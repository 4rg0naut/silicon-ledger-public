# 06 — Measuring the ANE: instruments, traps, and protocol

This file is about seeing and measuring what the Neural Engine is actually doing — not about
APIs, and not about bugs for their own sake. It catalogues every instrument available to an
outside observer, states for each what question it can answer, what it cannot, and how it
misleads, and ends with a measurement protocol we would trust ourselves to re-run.

The single most important lesson in here is not about hardware at all: **almost every wrong ANE
conclusion in our own record came from a tool that answered when it should have stayed silent.**
Four separate fabricated signals are documented below (a frozen energy channel, a free-running
clock, a process-scoped trace that misses the engine, and a power sampler that disagrees with
itself by 200×). Every one of them produced a confident, wrong number.

---

## 1. `enginemon` — the unprivileged instrument we built

`tools/enginemon/` is a single-file C tool (~317 lines) that reads Apple's private **IOReport**
counters directly and reports per-engine activity: CPU/GPU power, and ANE memory traffic plus
interrupt counts. It exists because the two standard instruments each fail in a different way —
`powermetrics` needs root, and `xctrace`'s `ane-hw-intervals` turned out to be blind to Core AI
graphs (measured: 0 intervals while a Core ML control in the same session logged 1310).

```bash
clang -O2 -o enginemon enginemon.c -framework CoreFoundation
./enginemon --list                                      # every engine channel it can see
./enginemon --interval 500 --duration 5                 # sample for 5 s
./enginemon --interval 500 --duration 25 -- <command>   # sample while a workload runs
```

**What it reads.** A single IOReport group is not enough, because ANE telemetry is spread across
several. `enginemon` copies and merges six groups into one subscription —
`Energy Model`, `AMC Stats`, `Interrupt Statistics (by index)`, `PMP`, `SoC Stats`, `GPU Stats`
— then samples with `IOReportCreateSamplesDelta`, so cumulative channels are differenced by the
framework rather than hand-subtracted. Private symbols are resolved with `dlsym` at runtime, so
the tool fails softly (`IOReport symbols missing`) if Apple moves something, instead of breaking
at link time.

**Why an unprivileged process can read it.** IOReport is private but stable, and an ordinary
process can list, subscribe to and sample it — verified on this machine at euid 501, macOS 27.0,
M4, with no helper and no entitlement. `powermetrics` and `xctrace` both require privilege;
`enginemon` does not. That is the whole reason it was written.

**The two fabricated signals it is built to avoid.** Both were hit during development, and both
would have produced a confident wrong answer:

1. **`Energy Model → ANE` is frozen.** It reads a constant (10945781) and never changes — not
   under idle, not under a Core ML workload that provably uses the ANE. Reporting its zero as
   "the ANE was not used" is a **fabricated negative**. The tool prints the value labelled as
   frozen and tells the reader to use other channels.
2. **`SoC Stats → ANE_*_TRIG` is a free-running 24 MHz clock.** It advances by exactly
   `elapsed × 24e6` regardless of load (measured: 5.46 s → 131110395 ticks). It looks like
   activity and means nothing. The tool excludes any channel whose name contains `TRIG`/`TRG`.

**The validated control comparison.** Controls run back to back, same machine, same session:

| channel | idle | Core ML `compute_units=ALL` (known ANE) |
| --- | ---: | ---: |
| `AMC Stats → ANE DCS RD` | 0 B | **128–171 GB** |
| `AMC Stats → ANE NRT AF RD` | 0 B | **184 GB** |
| `Interrupt Statistics`, subgroup `ane 0`, 2nd-level count | 0 | **24,538 – 37,368** |
| `PMP → ANE0 RD` | 0 events | 29,252 |
| `Energy Model → GPU Energy` | ~15 mW | ~14 mW (GPU idle — the ANE did the work) |
| `Energy Model → ANE` | 0 | **0** ← dead channel |

Read `AMC Stats` (bytes moved) and the `ane 0` interrupt counts. Those are the signals that
separate "the ANE worked" from "the ANE was idle".

**The traps inside the tool itself.**

- The ANE interrupt rows belong to **subgroup `ane 0`**. The `dart-ane 0` rows stay at 0 for ANE
  compute; the tool tracks both, so read the subgroup column or you will read the wrong zero.
- Channel availability is SoC- and OS-specific. Run `--list` first on a new machine; a channel
  that does not exist here may exist there, and vice versa.
- **`enginemon` cannot see ANE power.** Running it unfiltered during an ANE workload, the only
  *power* channel that moves is `GPU Energy`. What it sees for the ANE is traffic and
  interrupts. Power needs a different instrument.
- Its one-line `ANE activity` summary sums the `ANE DCS RD` channels and the `Handler Count`
  interrupt rows. It is a convenience, not a second measurement.

---

## 2. IOReport — what it is, and which channels to trust

IOReport is Apple's private performance-counter subsystem (`libIOReport.dylib`): a set of
grouped, named/typed counters that drivers publish, which a client subscribes to and samples.
It is the substrate under `powermetrics` and under `aneperf` (a Go tool that samples ANE energy,
power-management state residency, interrupt statistics and a small GPU surface through IOReport
plus the IOKit `H11ANEIn` service, loaded via `purego` — no cgo, no root). Both projects note the
same caveat: the API is undocumented and may change between macOS versions.

`aneperf` documents the group structure more completely than we had catalogued ourselves:

| group | contents |
| --- | --- |
| **Energy Model** | energy consumption values (mJ / uJ / nJ) |
| **PMP** | `SOC Floor` voltage states (VMIN/VNOM/VMAX); `DCS Floor` frequency states (F1–F6); `Fast-Die CE` compute-utilization histogram (0–100 % buckets); `AF BW` / `DCS BW` / `SOC-NI Util BW` bandwidth tiers; `PWRS` throttle-event counters |
| **Interrupt Statistics** | per-index interrupt handler counts |

`aneperf` derives `ane_utilization_pct` (compute utilization) and `ane_cluster_active_pct`
(cluster power residency) from the PMP histogram and residency states. These derived metrics are
the closest thing to a genuine ANE utilisation number available to an unprivileged process — but
note that they are IOReport *residency buckets*, not measured FLOPs, and we have not validated
them against a control on this machine.

**Trustworthy** (established by the control comparison above): `AMC Stats` byte counters, the
`ane 0` interrupt handler counts, `PMP → ANE0` events, `Energy Model → GPU Energy`.
**Not trustworthy**: `Energy Model → ANE` (frozen on this M4) and `SoC Stats → ANE_*_TRIG`
(free-running clock).

A zero is only meaningful for a channel that is *known to move*. That property is established by
running the controls, once, on the machine in question — which is exactly why `enginemon`
ships its control table in its README rather than just its channel list.

---

## 3. The other instruments

### 3.1 `powermetrics`

Needs `sudo`. Samples named rails (`ane_power,gpu_power,cpu_power`) and prints lines such as
`ANE Power: 0 mW`, `GPU Power: 37 mW`, `CPU Power: 335 mW`, `Combined Power (CPU + GPU + ANE)`.

**Answers:** average power per rail over a window, on a Mac. On this machine it is *the* direct
ANE power measurement — when the workload genuinely uses the ANE it reads correctly. EXP-003's
Core ML control: `ALL` → ANE **2463 mW mean, 3399 mW peak**; `CPU_ONLY` → ANE **6 mW** (the idle
floor).

**Cannot:** attribute power per-process (rails are whole-system, so the machine must be idle
apart from the workload); say anything at all about *placement* on its own — a zero ANE reading
means "the ANE was power-gated", which is what you get both when the work never ran there and
when it ran but the graph was trivially small.

**How it misleads — three ways, all observed:**

1. **Wrong zeros are sometimes right zeros.** EXP-004 read ANE **0.0 mW** in every arm of a
   Core AI `neuralEngine` run and we initially concluded the instrument was blind to Core AI.
   It was not: that graph (fp32) had **0 ANE regions** and genuinely ran on the GPU (GPU rail
   4421.6 mW). The later fp16 bundle — which does form ANE regions — reads **~1.9 W under load
   vs 8 mW idle**. The claim "both standard ANE instruments are blind to Core AI" was wrong and
   has been corrected.
2. **The sampler is not self-consistent.** Two runs of the *same* Core AI workload disagreed by
   ~200×: a validated parser averaged **1914 mW** at 500 ms, while a 200 ms phase-resolved run
   reported **~0 mW for ~11 of the 13 s** — during which the run performed 6,000 inferences at
   2.14 ms, and `enginemon` saw 173 GB of ANE traffic and 27,784 interrupts over an equivalent
   run. Two readings of one workload that far apart mean **`powermetrics`' `ane_power` sampler
   cannot adjudicate Core AI placement or state.**
3. **Output format is version-sensitive.** `bench/power_ab.py`'s docstring says so explicitly:
   the raw log is the deliverable, and the inline summary is best-effort because `powermetrics`'
   exact wording varies between macOS releases. A parser that silently drops samples produces
   fabricated numbers — see §3.4.

`xctrace`'s **Power Profiler** template is *"not supported on macOS"*, so on the Mac there is no
trace-based power path at all; `powermetrics` is it.

### 3.2 `xctrace` / Instruments — `ane-hw-intervals`

The `ane-hw-intervals` table is documented in the trace as *"Denotes an interesting period of
activity in the ANE"*. It is extractable headlessly:

```bash
xcrun xctrace export --input <trace> \
  --xpath '/trace-toc/run[@number="1"]/data/table[@schema="ane-hw-intervals"]'
```

`bench/ane_report.py` wraps that: it counts intervals, sums duration, reports longest/mean, and
looks for labels containing `Prediction` (observed: *Neural Engine Prediction*).

**Answers:** whether the ANE was busy during a window, how many disjoint jobs it ran, and how
long it was busy. EXP-003 is the clean case: Core ML `ALL` → **261 intervals, 503.79 ms busy**,
while `CPU_ONLY` → **0**. Subtracting one **361.41 ms** interval (the first-use ANE program
load/compile) leaves 260 intervals totalling **142.38 ms ≈ 0.55 ms per inference ≈ 75 %** of the
0.73 ms wall time — i.e. the trace tells you not just *that* the ANE ran but roughly how much of
the wall time it owned.

**Cannot:** see Core AI graphs. This is measured, not suspected. In EXP-004 the Core AI
granite `neuralEngine` run registered **0** ANE intervals while a MiniLM Core ML `ALL` control in
the same session registered **269** (511.48 ms, labelled *Neural Engine Prediction*). Repeating
system-wide with `--all-processes` — so an out-of-process ANE dispatch would also be captured —
still gave **0** for Core AI against **1310** intervals (1012.41 ms busy, mean 0.77 ms) for the
control. That rules out process scoping as the explanation.

**How it misleads:**

- **Absence of intervals is not absence of work.** A zero here means "this instrument cannot see
  this runtime", not "the ANE was idle". Core AI is the demonstrated case; treat 0 as *unknown*.
- The first interval on a cold model is the **program load/compile**, not inference. In EXP-003
  it was 361.41 ms against ~0.55 ms of real work per inference; counting it would have made the
  ANE look 20× slower than it is.
- The table is **machine-wide**, so attribution is only valid if a clean control ran in the same
  window — which is how EXP-003 justifies its 261-vs-0 pair.
- Interval count tracks **submissions**, and submission count tracks the static region count.
  A trace showing 25 submissions per pass is showing 25 regions, not 25 layers' worth of extra
  work: the same encoder gives the ANE 147.6 ms of work via Core AI's 25 submissions and
  150.4 ms via Core ML's single submission — within 2 %. What differs is delivery: Core AI is
  **28.7 % idle** across the window (median inter-submission gap 1.125 ms) against Core ML's
  **0.4 %**.

**The Core AI trace template contains no placement information.** A `Core AI` trace exposes 36
tables; the Core AI-specific one is `ODIEProfile` (9,127 rows for a 22.8 s run), whose columns are
`model-name`, `base-function-name`, `function-name`, `phase`, `category`, `color`, `level`,
`activity` and timing. Observed values: `category` = Inference 6080 / Setup 3043 / Load 4;
`phase` = Inference 9123 / Load 4. **There is no compute-unit or engine attribution anywhere** —
no per-op "landed on X" column and no per-engine lane. Nor is there an ANE template: the full
template list is 25 entries (Activity Monitor … Core AI, CPU Counters, CPU Profiler, Foundation
Models, Metal System Trace, Power Profiler, Processor Trace, System Trace, Time Profiler), *none*
ANE-specific. `metal-gpu-intervals` **does** attribute by process and is therefore the best
in-trace signal for a Core AI run — the granite `neuralEngine` run drove **54,846 Metal GPU
intervals** (61,920 command buffers, 113,172 GPU-state intervals) while registering zero ANE ones.

**Instruments Time Profiler** answers a different question — *which code paths* ran. Call the
model ~100 times in a loop, run the Time Profiler template, open the Call Tree, find
`-[MLNeuralNetworkEngine predictionFromFeatures:...]`, and **Focus on subtree**. When the ANE is
used there is a call to `-[_ANEClient evaluateWithModel...]`, which appears to measure the ANE
execution time. This is a sampling profiler over host code: it tells you the framework path, not
the hardware's utilisation.

### 3.3 Espresso `[CostModelFeature]` logs and `log stream`

Espresso (Core ML's private engine framework) logs per-op cost estimates under the
`[CostModelFeature]` tag, and prints `Unsupported op` compiler messages naming the reason a layer
did not land on the ANE. `anemll-profile` captures them by **forking `/usr/bin/log stream`** and
parsing the output; that is how it produces its `CPU/GPU Fallback` section with specific reasons
(e.g. *"Cannot support standalone slice_update"*, *"Unsupported tensor data type: int32"*).

Directly, on a Mac:

```bash
log stream --predicate '(subsystem IN {"com.apple.espresso","com.apple.coreml"}) && (category IN {"espresso","coreml"})' --info --debug
```

**Answers:** *why* a layer fell off the ANE, and the compiler's own cost estimate for each op.
This is the only instrument that explains a placement decision rather than observing its
consequence.

**Cannot:** give ground truth about what ran. These are compile-time estimates and diagnostics.

**How it misleads:** model and layer names appear as `<private>` in the logs unless a device
profile is installed to expose them (the community workaround is documented on Super User). A
log line saying an op is unsupported is a statement about the compiler's static analysis at that
moment on that toolchain, not about the silicon.

### 3.4 `MLComputePlan`

`MLComputePlan` is the public Core ML API that returns the compiler's per-op device assignment
(and cost weights) for a model. `ane-probe` uses it as a *scanner*: for each MIL op it builds a
minimal single-op Core ML program, converts it, compiles it, and queries the plan for which of
CPU/GPU/ANE support that op.

**Answers:** which ops are ANE-eligible on this machine/OS/coremltools combination. Our run on
this M4 (macOS 27.0, coremltools 9.0): **168 ops scanned, 130 built and queried, 100/130 =
76.9 % ANE-supported.** Every dense-transformer op is capable (`matmul, linear, conv, add, mul,
sub, softmax, gelu, relu, layer_norm, gather, transpose, reshape, reduce_mean, exp, erf, rsqrt,
pow`); the 30 that are not are transcendentals, index/control-flow, the scatter family, the RNN
family and randomness. `anemll-profile` loads a *whole* plan and analyses the ordered ops to find
**ANE graph interruption islands** — runs of non-ANE ops that break continuous ANE execution,
including GPU detours, ranked by an estimated boundary penalty (300 ms by default,
`--interrupt-ms` / `--interrupt-boundary-ms` to tune).

**Cannot:** report what the hardware did. It is static compiler analysis, and the docs say so:
*"Compute plan results reflect the compiler's static analysis. Actual runtime behavior may vary
with model context and input sizes."*

**How it misleads:**

- **`preferred` is meaningless for single-op models.** The README is explicit: because a
  one-op model pays the data-transfer cost to reach the ANE, the framework accounts for that
  overhead and normally chooses CPU. Only the `supported` column is informative. On this M4 the
  scan shows `preferred=ANE` on exactly 1 of 168 rows.
- **Spot checks lie; full scans do not.** An ad-hoc `ane_probe check conv` reported
  `conv → ANE: NO`; the full scan reports `conv → ANE: YES`. The hand-picked parameters were the
  artifact. The skipped ops (38 of 168) are a probe limitation, *not* evidence about the ANE.
- **It can abort the process.** `MLComputePlan.load_from_path` on an `.mlpackage` aborts with a
  C++ exception and takes buffered stdout with it — flush, or run it out-of-process.
- **A high ANE op count is not a residency claim.** On a real frame graph the plan reported
  11,412 ops with 4,303 assigned to the ANE and 0 to GPU and 0 to CPU — but the guidance that
  accompanies it is: *count ANE residency, never infer it.*

### 3.5 Region counting — the static instrument you can run in a shell

For Core AI bundles, the fraction of the graph compiled for the ANE is visible on disk:

```bash
find <bundle>.aimodelc -name '*ANE_region_*.mlir.bc' | wc -l   # 0 = silent GPU fallback
```

`coreai-build` exits 0 with **0 regions** when the ANE compiler rejects a graph (4-bit group-8
palettization does this), so a nonzero exit code is not a placement signal — the file count is.
`coreai-build inspect <bundle>` also prints `This device's architecture` (ours is **h16g** for
M4; `h16c` is M4 Max — compiling for the wrong variant wastes a ~10 GB build).

**Traps:** the glob must be `*ANE_region_*.mlir.bc`. An earlier count used
`find <bundle> -name '*ANE_region*'`, which matches a **directory and the file inside it** and
therefore double-counts every region — 14 where the truth was 13, 2 where it was 1. A metric used
as a gate cannot be off by one (recorded as F-27). And region count is a **shape** metric, not a
quality metric: the same graph at 13 regions and 122,832 interrupts and at 1 region with 13,472
interrupts moved ~88 GB either way, and the 1-region build was the fast one (F-26). Fewer,
larger regions means fewer ANE↔GPU segment boundaries.

---

## 4. Placement detection — did it actually run on the ANE?

There is **no public API** to ask at runtime which piece of hardware Core ML is using, and Core ML
may split one inference across several processors. Placement therefore has to be established by
side effects. In rough order of rigour:

**Debugger and breakpoints (device, Xcode).**

- Pause during a run: a thread named **`H11ANEServicesThread`** means Core ML is using the ANE for
  at least some part of the model.
- Symbolic breakpoint on **`-[_ANEModel program]`** — if it is hit, Core ML is using the ANE.
  (Spelling matters, including the leading dash.)
- Core ML's three Espresso engines are **ANE `Espresso::ANERuntimeEngine`**, **GPU
  `Espresso::MPSEngine` / `Espresso::MetalLowmemEngine`**, **CPU `Espresso::BNNSEngine`**. For
  guessing the *other* engines: `Espresso::MPSEngine::context::__launch_kernel`,
  `Espresso::BNNSEngine::convolution_kernel::__launch`,
  `Espresso::elementwise_kernel_cpu::__launch`, or fall back to
  `Espresso::layer::__launch` / `Espresso::net::__forward`.
- **These symbols change between OS versions.** Dump the live set with
  `image dump symtab <path-to-Espresso>` after `image list Espresso`.
- **A hit on `-[_ANEModel program]` does not mean the whole model ran on the ANE.** It means at
  least part of it did; you need the GPU/CPU breakpoints too to bound the split.

**Placement by latency comparison.** Change `computeUnits` from `.all` to `.cpuAndGPU` and
`.cpuOnly` and compare. If `.all` is not much faster, Core ML may be using the ANE for only part
of the model — or not at all.

**Placement by power.** The A/B in `bench/power_coreai.py`: run the identical workload once per
compute-unit preference while sampling the rails. ANE rail high on `neuralEngine` and idle on
`cpuOnly` → the ANE really ran it; GPU rail high on `neuralEngine` → the preference fell back to
the GPU; neither rail moves → CPU fallback.

**Placement by IOReport traffic and interrupts.** `enginemon`'s control pair (§1). This is the
one that works unprivileged and is not tied to a runtime — verified on Core AI, which the traces
cannot see.

### Traps in placement detection

- **`preferredComputeUnitKind` is a preference over a heterogeneous allowed set.** `.cpu` and
  `.gpu` declare the *same* `allowedComputeUnitKinds` — `[cpu, gpu, neuralEngine]` — and differ
  only in which is preferred; that preference is a partitioning input and can place a region on a
  different unit, silently changing the numbers. Use `cpu_only()` for parity work, never
  preferred `.cpu`. The blast radius runs from rounding-scale to anti-correlated.
- **A distinct latency profile is not a distinct execution unit.** EXP-004's Core AI
  `.neuralEngine` arm was 4.331 ms with a 0.015 ms spread, against `.gpu` at 4.982 ± 0.461 ms —
  non-overlapping ranges, ~30× more deterministic. It looked like separate hardware. It was a
  different **GPU schedule**: power rails and Metal intervals both showed the GPU. Recorded as
  F-22.
- **`--compute` does not override an AOT bundle.** An fp16 AOT bundle moves ANE bytes under both
  `--compute neuralEngine` (101.6 GB) and `--compute gpu` (91.2 GB), while `--compute cpuOnly`
  drops to 0 interrupts. The compile-time choice is baked in; a runtime "preference" is not a
  control.
- **Placement is a property of how a computation is expressed, not of what it computes.** The
  measurement study arXiv 2608.22110 found a fused RMSNorm that is fully ANE-eligible while its
  arithmetically identical decomposition is CPU-only. The same paper found **weight encoding
  gates the accelerator**: a 25.85 M-parameter conv-heavy fp16 model was assigned entirely to the
  CPU with zero bytes through the engine (their counters confirm it), while the same graph in
  int8 or 2-bit returned to ~83 % residency and ran 1.8–2.2× faster, and a smaller 22.29 M
  all-attention fp16 model sat at 98.9 %. **What the compiler intended and what ran can differ;
  read the byte counters.**
- **The accelerator-contention differential does not work on this machine.** The idea — an
  ANE-saturating hog must slow an ANE-bound process, a GPU-only hog must not — failed its own
  positive control: the GPU-bound granite arm slowed only **1.10×** under a CPU+GPU hog, below
  the 1.15× threshold. Every row of that matrix is void. It is recorded as a failed method, which
  is more useful than its numbers.

---

## 5. Effective throughput measurement

### What to measure

For a weight-streaming workload the meaningful number is **effective bandwidth** — bytes moved
per unit time — because that is usually the binding constraint. Two derivations are in use:

- From the substrate: `AMC Stats` bytes ÷ elapsed (§1). This gives you what the engine actually
  streamed.
- From the outside: `effective GB/s = bytes-per-token ÷ measured tok/s`, compared against what a
  clean stream achieves on the same silicon (A19: mixed/Gemma workloads ~44 GB/s; clean int8
  dense has measured into the 60s). If the engine is already near that ceiling there is nothing to
  harvest. This audit-before-proposing rule is the "never blame the model" discipline.

A roofline calibration for the M3 from the DMA work: LPDDR-6400 is 128 bit × 6.4 GT/s =
**102.4 GB/s**, which checks out against the advertised ~100 GB/s. Sustained DRAM bandwidth is
the DQ-pin utilisation — every GB/s short of the ceiling is a cycle the data lines sat idle.

### Median beats mean, and why

ANE latency is **bimodal** on this M4. A 20,000-inference run showed samples 0–830 in the *fast*
state and 831–20,000 in the *slow* state — 19,169 consecutive, no flipping back. The transition
is **one-way within a run**. Across runs, the fast state is a *burst* condition: ten back-to-back
bursts of 120 inferences were fast (2.13–2.25 ms) in 8 of 10, while a 1,200-inference run in the
same period had a fast phase of only 258–385 samples. It does not recover with idle (45 s → 6 of
2,000 fast; 4 minutes → 21 of 1,500), page-cache residency is irrelevant (pre-reading the 186 MB
weights file made it *worse*), and there is no thermal warning.

The practical consequence: repeating an identical run gave medians of **2.14, 2.15, 2.15, 2.17,
2.40, 3.38, 3.77, 4.26, 4.60, 4.90 ms** while `min` stayed at **1.78–1.90 ms in every run**. A
4,000-iteration run is not enough to converge the median. So:

- **`min` is the stable statistic** — the fast state is always reachable.
- **Medians must be reported with a range**, because a single-run ANE latency for this workload
  carries up to a **2.1× spread** and which state dominates is decided per run, not by run
  length.
- The two states differ by ~2.1× in **both** latency and effective bandwidth (fast: 1.85–2.25 ms,
  ~31 GB/s; slow: ~4.75 ms, ~14.5 GB/s). Both figures moving together by the same factor is the
  signature of a **clock/throughput** change, not a data-location change — a cache effect would
  alter bytes moved, not the rate.

The cause is still unidentified. Thermals are excluded (`pmset -g therm` clean; the machine is far
too efficient to throttle in 2 s), page cache is excluded, and the GPU shows the same burst shape.
Candidates: ANE power/clock management with a long recovery constant, or arbitration with another
ANE client (macOS runs `mediaanalysisd` and `photoanalysisd`). An idle 20 s `enginemon` monitor
showed 0 B / 0 interrupts, so it is not a persistent background user.

### Interleaving: why runs must alternate

On any thermally-throttling machine, block-ordered measurement measures the *order*, not the
engine. Measured examples:

- On an iPhone 17 Pro under sustained load, the ANE 8-bit 1B drops from 76 to ~52 tok/s at the
  `fair → serious` thermal transition (~70 s in, wired + screen on). **First-minute numbers are
  not sustained numbers.**
- A block-ordered first attempt had ExecuTorch decaying 23.5 → 17.4 tok/s inside its own block.
- LiteRT's own fresh decode spread ±6 tok/s within one afternoon on one device. A single
  historical number is not decision-grade.
- Day noise is ±1.4 tok/s on the Gemma-4 A19 work: cross-configuration claims need interleaved
  A/B, not different-day numbers.
- On a fanless M3 Air the DMA work interleaved baseline and scrambled-address samples
  **run-to-run** specifically so thermal ramp hit both conditions equally.

The working protocol in the zoo: order **A-B-A-B** (N arms: A-B-C-A-B-C) with **20 s idle between
launches**, each launch a **fresh process**, and report **the two rounds' values, never one
number**. For sustain work, idle ≥3 min *and until `ProcessInfo.thermalState` returns to `fair`
or below* (cap 10 min) before loading the next arm — v1's fixed 3 min let the second arm start at
`serious`. Also: a locked screen caps the GPU, so order must not decide the result; benchmark
**serially** — an overlapping palettization run inflated one sweep and every number had to be
retaken.

### How the DMA erratum write-up structured its measurement

Worth copying, because it produced a finding that two rounds of conventional benchmarking would
have missed:

1. **Isolate one variable at the register level.** The claim is about the kernel DMA engine, so
   the sweep changed only the DMA size and address; a hexdiff of the executed register file
   (`TD+0x078` core bases, `TD+0x0b0–0x0f0` core sizes, `TD+0x134` `Common.Cin`, `TD+0x1f0`
   L2 source stride, `TD+0x214` L2 result base) is shown to prove it.
2. **Median, not mean, over repeated replicas.** At N=4096 the table reports *median µs per
   replica* for three replicas (rep a/b/c) per D. D=2048 is ~997 µs in all three; D=2016 ~290 µs.
   In GB/s: 16.93 vs 44.51 — a **27.57 GB/s (62 %) collapse**.
3. **Interleave the conditions to defeat thermal drift.** The scramble control was run
   interleaved with baseline, run-to-run, on a fanless M3 Air — explicitly so any thermal ramp hit
   both equally. Result: baseline median 31.37 GB/s vs scrambled 32.29 GB/s, i.e. address
   scrambling explains ~1 GB/s of a ~200 % effect.
4. **Sweep the whole aperture, then look for periodicity.** Sweeping D across its whole range
   found a *resonance* at D=2048 and, critically, that **all integer multiples of 2048** collapse
   to the same 17–19 GB/s floor.
5. **Separate confounded variables by inverse sweeps.** Since the original plots swept D with N
   fixed, D and N·D were confounded. Sweeping D and N *inversely* so all tasks compile to the
   same 1 MiB of static kernel data per core isolates the cause: any D×N combination totalling
   1 MiB/core collapses.
6. **Run the null control for the fix.** Splitting a 1 MiB transfer: one `0x4000`-line task
   17.25 GB/s → two `0x2000`-line tasks **45.52 GB/s (2.66×)** → four `0x1000`-line tasks
   44.83 GB/s. The control — splitting a transfer that was *not* a 1 MiB multiple (1 MiB − 16 KiB)
   — gives **no speedup at all**. That is what makes the 2.66× attributable to the erratum rather
   than to dispatch size.
7. **Report the confound you could not remove.** The results table shows the effect scaling with
   size (17.3 → 19.1 GB/s unsplit and 43.5 → 60.5 GB/s fixed across D = 2048…16384, speedup
   2.51× → 3.16×), so the headline is stated as a range, not one number.

The mechanism, in brief, is a 14-bit prefetch-ring pointer: 0x4000 lines = 1 MiB, the ring's
distance arithmetic aliases "one full lap remaining" to "empty" and starves its own prefetch, so
the transfer runs on the slow no-speculation path at 17–19 GB/s. The notch recovers within
**±256 lines = 16 KiB = one page** of the boundary; every k-th lap's bandwidth curve collapses to
the same line after recentering by k·0x4000, with a ramp of **3.18·k µs/line** (R² 0.96–0.99 per
lap). It is not core contention (latency is constant from 1 to 16 active cores) and it is not
DRAM bank aliasing (the scramble test above). The software fix is to avoid requesting exactly
1 MiB kernel transfers; Llama 3.2 1B went **10.0 → 24.3 tok/s** and Qwen3-8B **1.36 → 2.97
tok/s**.

**Scope:** M3 specifically. `anemll` states M1 and M5 Max are unaffected, and reports that 7 of
ANEMLL's 15 models were affected. That is a single-source claim about the other chips.

### Peak-throughput measurement on the private path

Two private-API projects measure the raw compute ceiling rather than a model's achieved rate:
`maderix/ANE` has `inmem_peak.m` (peak TFLOPS via a 2048×2048 matmul), `sram_bench.m` /
`sram_probe.m` (SRAM bandwidth and size/layout), `inmem_bench.m` (dispatch latency) and
`ane_int8_bench.m` (int8 W8A8 vs fp16). Its reported M4 numbers: **fp16 18.6 TOPS, int8 W8A8
35.1 TOPS — 1.88×**, with int8 activations halving L2 SRAM bandwidth between tiles via MIL
`quantize`/`dequantize`. Its own honesty check is the important part: training utilisation is
**5–9 % of peak** with many element-wise ops still falling back to CPU. And `libane` claims
matmul-as-conv1×1 gives **3× throughput over MIL matmul** on the ANE, citing arXiv 2603.06728 —
that is a project claim we have not reproduced.

---

## 6. Power measurement

### Why it is hard

- **Rails are whole-system.** No per-process ANE power exists. Attribution requires an otherwise
  idle machine, and a control arm.
- **The one Mac instrument needs root** (`powermetrics`), and the Mac trace template that would
  do it (`Power Profiler`) is not supported on macOS.
- **The unprivileged instrument cannot see power at all.** `enginemon` sees ANE traffic and
  interrupts; `Energy Model → ANE` is frozen on this M4.
- **The root instrument is not reliably self-consistent** — see the 200× disagreement in §3.1.
- **Energy, not power, is what usually matters.** Convert to energy per unit of work
  (`mJ/embedding`, `mJ/token`) or the comparison reduces to "who finished first".

### What the community measures, and how

The zoo's pattern is a paired A/B of the *same* workload at different placements, with the rails
sampled underneath, and energy derived per unit of work:

| | ANE (Core ML `ALL`) | CPU-only | ratio |
| --- | ---: | ---: | ---: |
| throughput | 1410 emb/s | 611 emb/s | 2.31× |
| **energy per embedding** | **2.06 mJ** | **11.45 mJ** | **5.6× less** |
| ANE power (mean) | 2463 mW | 6 mW (idle) | — |
| CPU power (mean) | 439 mW | 6983 mW (peak 9483) | 16× lower |
| GPU power (mean) | 0.0 mW | 2.4 mW | work went to the ANE |

The headline pattern to carry forward: **the efficiency win is much larger than the speed win**,
and the ANE finishes so fast it spends less total energy *while drawing ~2.5 W*. The same shape
appears on Core AI: an fp16 ANE-resident bundle draws ~1.9 W under load against 8 mW idle (~240×),
and against 4124 mW for the same bundle forced onto the GPU. So the ANE's durable advantage in
our measurements is **energy and load time**, not sustained throughput — a sharper and better-
supported claim than "the ANE is 2× faster".

### `bench/power_ab.py` and `bench/power_coreai.py`

**`power_ab.py`** — A/B the *same Core ML workload* at `ALL` vs `CPU_ONLY`. It requires root,
refuses politely otherwise. Method: build the model at each compute unit, run 10 warm-up
inferences (which includes the ANE program load), start `powermetrics --samplers
ane_power,gpu_power,cpu_power -i 500`, **sleep 2 s so the sampler settles**, then loop predictions
for `--seconds` (default 15); terminate the sampler, write the raw log to
`bench/power_<case>.txt`, and report per rail `mean`, `max`, and `mJ/embedding`. Its docstring
states the design rule plainly: **the raw files are the deliverable** — the inline summary is
best-effort because `powermetrics`' exact wording varies between macOS releases.

**`power_coreai.py`** — the same idea for a Core AI graph, running the `granite-runner` binary
once per compute-unit preference (`neuralEngine`, `gpu`, `cpuOnly`), 3000 iterations each. Same
2 s settle, same 500 ms interval, raw logs to `results/EXP-004-coreai-ane/raw/power_<compute>.txt`,
and it reuses `power_ab.parse_power` so both tools parse identically. Its stated interpretation
rules are the useful part: ANE rail high on `neuralEngine` and idle on `cpuOnly` → the ANE ran
it; GPU rail high on `neuralEngine` → the preference fell back; neither rail moves → CPU.

**The bug worth remembering (F-29).** A third script, `power_phase_probe.py`, first reported ANE
power of 0–14 mW and CPU up to 6.6 W for the same workload that `power_coreai.py` read as
1914 mW. It was not an instrument conflict — it was a **bug in the probe's parser**, which
chopped the `powermetrics` output with its own regexes and silently dropped most samples (14
parsed where ~51 were expected). The fix was threefold and is the model to copy: **use the one
validated parser**, **write the raw log so any disagreement is checkable**, and **refuse a verdict
when either window has fewer than 3 samples**. The sibling bug (F-28) is the same family: a probe
that printed a verdict with n=1 in one window after the run never entered the state being
probed. **A tool that answers when it should stay silent is how confident wrong results get
published.**

---

## 7. A recommended measurement protocol

Distilled from everything above. The order matters: placement before speed, and a control before
either.

**0. Pin the machine state.** Record macOS build, Xcode/toolchain version, chip and architecture
(`coreai-build inspect` prints it), model/bundle hash, sequence length, dtype/quantisation recipe,
and whether the machine is on battery or charging, screen on or locked. Numbers from different
builds are not comparable — a phone OS update mid-session colds every specialization cache, and
in one zoo session that happened and invalidated cross-build comparisons.

**1. Establish a control pair first.** Before believing any ANE number, run the positive/negative
control on *this* machine and *this* OS:
- positive: a workload known to use the ANE (Core ML `compute_units = .all` on an ANE-shaped
  graph measured **128–171 GB / 24,538–37,368 interrupts** here);
- negative: the same graph `CPU_ONLY`, expecting **0 B / 0 interrupts**.
If the positive control does not move, the instrument is broken and no conclusion from it is
valid. Run `enginemon --list` on a new machine before anything else.

**2. Establish placement separately from speed.** Use at least two independent instruments that
fail differently — IOReport traffic/interrupts, the power rails, `ane-hw-intervals` (Core ML
only), Metal intervals (Core AI), region counts, `MLComputePlan`. Do not accept a latency
signature as evidence of a unit (F-22). Count residency; never infer it. Beware
`preferredComputeUnitKind`: for parity work use `cpu_only()`, and remember `--compute` cannot
override an AOT bundle.

**3. Measure latency with the fixed protocol.** 10 discarded warm-up calls, then 100 measured
calls back to back in a single process; report **p50, p95, and min**, and **state the work unit
explicitly** (`per embedding`, `per decision`, `per token`). Report `ms/token` when comparing
across model classes, because tokens are the only unit that means the same thing for an embedder,
a reranker and a decision model. The corpus this replaces had 142 latency figures under at least
four conventions, no stated warm-up, and no normalisation — real numbers that were not
comparable.

**4. Interleave the arms.** A-B-A-B (A-B-C-A-B-C for three), fresh process per launch, ≥20 s idle
between launches, and report both rounds rather than one number. For sustained runs, idle until
`thermalState` returns to `fair` or below (cap 10 min) before loading the next arm, and log
elapsed time, thermal state and battery per trial. Never compare across days or across a run that
overlapped other load: an overlapping job inflated one of our sweeps and every number had to be
retaken.

**5. Report a range, not a point, for ANE latency.** Give `min` as the stable statistic and the
median together with its observed spread. Where the state governs the answer (burst vs
sustained), report both windows and, if a transition was measured, the sample index at which it
occurred — that ordering is what distinguishes a one-way transition from noise.

**6. Compute bandwidth, don't just time.** `GB/s = bytes moved ÷ elapsed`, where bytes come either
from the IOReport `AMC Stats` counters or from weight bytes per token. Compare against the clean
stream ceiling on the same silicon before claiming a kernel win. Re-derive energy per unit of
work from the rails. Keep the raw logs.

**7. Only then vary one thing.** dtype, layout, region count, weight encoding — one at a time,
with the confound named when it cannot be removed (the DMA study's inverse D/N sweep, or its
scaled speedup range, are the models).

**8. Record the negative controls and the failed methods.** The most valuable entries in our
record are "the contention differential was void" and "the probe answered with n=1". A
measurement file that only keeps successful runs teaches the wrong lesson.

### The traps, in one table

| instrument | answers | cannot answer | how it misleads |
| --- | --- | --- | --- |
| `enginemon` / IOReport `AMC Stats` + `ane 0` interrupts | did the ANE move bytes / take interrupts | power, utilisation %, placement of a *runtime* | reads 0 when the channel does not exist; `dart-ane 0` is the wrong zero |
| IOReport `Energy Model → ANE` | nothing on this M4 | anything | **frozen constant** — its zero is a fabricated negative |
| IOReport `SoC Stats → ANE_*_TRIG` | nothing | anything | **free-running 24 MHz clock** — looks like activity |
| `powermetrics` rails | mean power per rail | per-process attribution; low-rate Core AI state | needs root; parser- and window-sensitive; disagreed with itself ~200× |
| `xctrace` `ane-hw-intervals` | ANE busy intervals and duration (Core ML) | anything about Core AI | **0 for Core AI even system-wide**; first interval is program load |
| `xctrace` `Core AI` template | per-function phases | placement of any kind | 36 tables, no engine column; no ANE template exists |
| Espresso `[CostModelFeature]` / `log stream` | *why* an op left the ANE | what ran | compile-time estimate; names are `<private>` |
| `MLComputePlan` | op-level device support | runtime behaviour | `preferred` meaningless for 1-op models; can abort the process |
| region count on disk | static ANE coverage | anything dynamic | wrong glob double-counts; shape metric, not quality |
| debugger breakpoints | which Espresso engine is live | the split, without several breakpoints | symbols move between OS versions |

---

## Records

```jsonl
{"id":"MEASURE-001","claim":"enginemon is a single-file C tool that reads Apple's private IOReport counters from an unprivileged process and reports per-engine activity for CPU, GPU and ANE.","kind":"definition","confidence":"documented","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","iobreport","placement"],"entities":["enginemon","IOReport"],"contested":false,"split":"train"}
{"id":"MEASURE-002","claim":"enginemon is built with 'clang -O2 -o enginemon enginemon.c -framework CoreFoundation'.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","build"],"entities":["enginemon"],"contested":false,"split":"train"}
{"id":"MEASURE-003","claim":"enginemon is invoked as './enginemon --list' to list channels, './enginemon --interval 500 --duration 5' to sample, and './enginemon --interval 500 --duration 25 -- <command>' to sample while a workload runs.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","usage"],"entities":["enginemon"],"contested":false,"split":"train"}
{"id":"MEASURE-004","claim":"A single IOReport group is insufficient for ANE telemetry, so enginemon merges the Energy Model, AMC Stats, Interrupt Statistics (by index), PMP, SoC Stats and GPU Stats groups into one subscription.","kind":"definition","confidence":"documented","source":"/Volumes/data/local_ai_stack/tools/enginemon/enginemon.c","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","iobreport"],"entities":["enginemon","IOReport"],"contested":false,"split":"train"}
{"id":"MEASURE-005","claim":"enginemon differences cumulative IOReport channels using IOReportCreateSamplesDelta rather than hand-subtracting successive samples.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","iobreport"],"entities":["enginemon","IOReportCreateSamplesDelta"],"contested":false,"split":"train"}
{"id":"MEASURE-006","claim":"The IOReport channel 'Energy Model -> ANE' is frozen on this M4 at the constant value 10945781 and never changes, neither at idle nor under a Core ML workload that provably uses the ANE.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","trap"],"entities":["enginemon","IOReport","M4"],"evidence":"frozen constant 10945781 under idle and under a known-ANE Core ML run","caveat":"observed on M4/macOS 27.0; other SoCs may expose a live channel","contested":false,"split":"train"}
{"id":"MEASURE-007","claim":"Reporting the frozen Energy Model -> ANE channel's zero as evidence that the ANE was not used is a fabricated negative.","kind":"gotcha","confidence":"inferred","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","trap"],"entities":["enginemon"],"contested":false,"split":"train"}
{"id":"MEASURE-008","claim":"The IOReport 'SoC Stats -> ANE_*_TRIG' channels are a free-running 24 MHz clock that advances by exactly elapsed times 24e6 regardless of load.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/tools/enginemon/enginemon.c","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","trap"],"entities":["enginemon","IOReport"],"evidence":"5.46 s elapsed produced 131110395 ticks","caveat":"measured on M4; the channel names exist on other SoCs","contested":false,"split":"train"}
{"id":"MEASURE-009","claim":"enginemon excludes IOReport channels whose names contain TRIG or TRG because they look like activity while carrying no load information.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/tools/enginemon/enginemon.c","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","trap"],"entities":["enginemon"],"contested":false,"split":"train"}
{"id":"MEASURE-010","claim":"In the validated control comparison, 'AMC Stats -> ANE DCS RD' reads 0 B at idle and 128-171 GB under a Core ML workload with compute_units=ALL that is known to use the ANE.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","iobreport","placement"],"entities":["enginemon","AMC Stats"],"evidence":"0 B idle vs 128-171 GB Core ML compute_units=ALL","contested":false,"split":"train"}
{"id":"MEASURE-011","claim":"In the validated control comparison, 'AMC Stats -> ANE NRT AF RD' reads 0 B at idle and 184 GB under a Core ML workload with compute_units=ALL.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","iobreport"],"entities":["enginemon","AMC Stats"],"evidence":"0 B idle vs 184 GB","contested":false,"split":"train"}
{"id":"MEASURE-012","claim":"In the validated control comparison, the Interrupt Statistics channel count under subgroup 'ane 0' reads 0 at idle and 24,538 to 37,368 under a Core ML workload with compute_units=ALL.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","iobreport","placement"],"entities":["enginemon","Interrupt Statistics"],"evidence":"0 interrupts idle vs 24,538-37,368","contested":false,"split":"train"}
{"id":"MEASURE-013","claim":"In the validated control comparison, the PMP channel 'ANE0 RD' reads 0 events at idle and 29,252 events under a Core ML workload with compute_units=ALL.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","iobreport"],"entities":["enginemon","PMP"],"contested":false,"split":"train"}
{"id":"MEASURE-014","claim":"Under a Core ML workload that runs on the ANE, the GPU Energy channel reports roughly 14 mW, about the same as its ~15 mW idle value, confirming the GPU was not the unit doing the work.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","placement"],"entities":["enginemon","Energy Model"],"contested":false,"split":"train"}
{"id":"MEASURE-015","claim":"The ANE interrupt rows in IOReport belong to subgroup 'ane 0', while the 'dart-ane 0' rows stay at 0 during ANE compute.","kind":"gotcha","confidence":"documented","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","iobreport","trap"],"entities":["enginemon","Interrupt Statistics"],"contested":false,"split":"train"}
{"id":"MEASURE-016","claim":"enginemon resolves private IOReport symbols with dlsym at runtime so it fails softly with an 'IOReport symbols missing' message rather than failing at link time if Apple moves them.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/tools/enginemon/enginemon.c","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","iobreport"],"entities":["enginemon"],"contested":false,"split":"train"}
{"id":"MEASURE-017","claim":"IOReport channel availability is SoC- and OS-specific, so enginemon --list should be run first on a new machine because a channel absent on one machine may exist on another.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","iobreport"],"entities":["enginemon"],"contested":false,"split":"train"}
{"id":"MEASURE-018","claim":"An unprivileged process on macOS 27.0 on an M4 can list, subscribe to and sample IOReport channels, verified at euid 501 with no helper and no entitlement.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","iobreport","privilege"],"entities":["IOReport","M4"],"contested":false,"split":"train"}
{"id":"MEASURE-019","claim":"enginemon cannot observe ANE power: during an ANE workload the only power channel that moves is GPU Energy, while what enginemon sees for the ANE is memory traffic and interrupt counts.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","limit"],"entities":["enginemon"],"caveat":"M4/macOS 27.0; the Energy Model -> ANE channel may be live on other SoCs","contested":false,"split":"train"}
{"id":"MEASURE-020","claim":"enginemon's one-line 'ANE activity' summary is the sum of the 'ANE DCS RD' byte channels and the 'Handler Count' interrupt rows.","kind":"definition","confidence":"documented","source":"/Volumes/data/local_ai_stack/tools/enginemon/enginemon.c","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation"],"entities":["enginemon"],"contested":false,"split":"train"}
{"id":"MEASURE-021","claim":"IOReport is Apple's private grouped performance-counter subsystem exposed through libIOReport.dylib, which a client subscribes to and samples.","kind":"definition","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/aneperf/README.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","iobreport"],"entities":["IOReport"],"contested":false,"split":"train"}
{"id":"MEASURE-022","claim":"aneperf samples ANE energy, power-management state residency, interrupt statistics and a small GPU metrics surface using Apple's private IOReport and IOKit APIs via purego without cgo.","kind":"definition","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/aneperf/README.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","iobreport"],"entities":["aneperf","IOReport","IOKit"],"contested":false,"split":"train"}
{"id":"MEASURE-023","claim":"The IOReport PMP group exposes SOC Floor voltage states VMIN/VNOM/VMAX, DCS Floor frequency states F1-F6, a Fast-Die CE compute-utilisation histogram bucketed 0-100%, AF BW / DCS BW / SOC-NI Util BW bandwidth tiers, and PWRS throttle-event counters.","kind":"definition","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/aneperf/README.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","iobreport"],"entities":["aneperf","IOReport","PMP"],"contested":false,"split":"holdout"}
{"id":"MEASURE-024","claim":"aneperf derives an 'ane_utilization_pct' compute-utilisation field and an 'ane_cluster_active_pct' cluster power-residency field from IOReport states.","kind":"definition","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/aneperf/README.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","iobreport"],"entities":["aneperf"],"caveat":"derived from PMP residency buckets, not from measured FLOPs; not validated by us against a control","contested":false,"split":"train"}
{"id":"MEASURE-025","claim":"Both IOReport-based tools document that these Apple APIs are undocumented and may change between macOS versions.","kind":"gotcha","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/aneperf/README.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","iobreport","fragility"],"entities":["aneperf","IOReport"],"contested":false,"split":"train"}
{"id":"MEASURE-026","claim":"powermetrics requires root on macOS.","kind":"fact","confidence":"documented","source":"/Volumes/data/local_ai_stack/bench/power_ab.py","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","privilege"],"entities":["powermetrics"],"contested":false,"split":"train"}
{"id":"MEASURE-027","claim":"powermetrics samples named power rails with '--samplers ane_power,gpu_power,cpu_power' and prints per-rail power lines plus a combined CPU+GPU+ANE figure.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/is-model-using-ane.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","power"],"entities":["powermetrics"],"contested":false,"split":"train"}
{"id":"MEASURE-028","claim":"A Core ML workload on the ANE measured with powermetrics reads an ANE mean of 2463 mW and peak of 3399 mW, against 6 mW on the same graph at CPU_ONLY.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-003-minilm-coreml-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","placement"],"entities":["powermetrics","Core ML","all-MiniLM-L6-v2"],"evidence":"ANE mean 2463 mW / peak 3399 mW (ALL) vs 6 mW (CPU_ONLY)","caveat":"M4/macOS 27.0, S=128, fp16, 15 s windows on an idle machine","contested":false,"split":"train"}
{"id":"MEASURE-029","claim":"The Core ML sentence encoder's energy per embedding was 2.06 mJ on the ANE against 11.45 mJ on CPU-only, a 5.6x energy advantage for only a 2.31x throughput advantage.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-003-minilm-coreml-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","efficiency"],"entities":["powermetrics","all-MiniLM-L6-v2"],"evidence":"2.06 mJ/embedding vs 11.45 mJ/embedding","contested":false,"split":"train"}
{"id":"MEASURE-030","claim":"The power rails are whole-system, so power A/B runs must be made on an otherwise idle machine to keep attribution valid.","kind":"gotcha","confidence":"documented","source":"/Volumes/data/local_ai_stack/results/EXP-003-minilm-coreml-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","method"],"entities":["powermetrics"],"contested":false,"split":"train"}
{"id":"MEASURE-031","claim":"Two runs of the same Core AI workload disagreed by about 200x on ANE power: a validated parser averaged 1914 mW at 500 ms, while a 200 ms phase-resolved run reported about 0 mW for roughly 11 of 13 s.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","contradiction"],"entities":["powermetrics","Core AI","enginemon"],"evidence":"1914 mW averaged vs ~0 mW for ~11 of 13 s; enginemon independently saw 173 GB and 27,784 interrupts over an equivalent run","contested":false,"split":"train"}
{"id":"MEASURE-032","claim":"powermetrics' ane_power sampler cannot adjudicate Core AI placement or ANE state, because two runs of one workload disagreed by roughly 200x.","kind":"open-question","confidence":"inferred","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","limit"],"entities":["powermetrics","Core AI"],"caveat":"the disagreement was traced on this machine only; the mechanism is unresolved","contested":true,"split":"train"}
{"id":"MEASURE-033","claim":"An earlier claim that both standard ANE instruments are blind to Core AI was wrong: the powermetrics ANE rail correctly read 0.0 mW for arms whose fp32 graphs compiled to 0 ANE regions and genuinely ran on the GPU.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","correction"],"entities":["powermetrics","Core AI"],"evidence":"fp32 Core AI arms: ANE 0.0 mW and GPU 4421.6 mW; fp16 ANE-resident arm: ANE ~1.9 W","contested":false,"split":"train"}
{"id":"MEASURE-034","claim":"powermetrics' exact output wording varies between macOS releases, so its raw output file is the deliverable and any inline parsed summary is best-effort.","kind":"gotcha","confidence":"documented","source":"/Volumes/data/local_ai_stack/bench/power_ab.py","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","method"],"entities":["powermetrics","power_ab.py"],"contested":false,"split":"train"}
{"id":"MEASURE-035","claim":"The xctrace Power Profiler template is not supported on macOS, so there is no trace-based power path on the Mac.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-004-coreai-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","limit"],"entities":["xctrace","Instruments","macOS"],"caveat":"observed with Xcode 27.0 on macOS 27.0","contested":false,"split":"train"}
{"id":"MEASURE-036","claim":"The xctrace ane-hw-intervals table denotes interesting periods of ANE activity and can be exported headlessly with 'xcrun xctrace export --input <trace> --xpath' targeting the ane-hw-intervals schema.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/bench/ane_report.py","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","tracing"],"entities":["xctrace","ane-hw-intervals"],"contested":false,"split":"train"}
{"id":"MEASURE-037","claim":"A Core ML run with compute_units=ALL produced 261 ANE hardware intervals and 503.79 ms of ANE busy time, while the same model at CPU_ONLY produced 0 intervals and 0.00 ms.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-003-minilm-coreml-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","tracing","placement"],"entities":["xctrace","ane-hw-intervals","all-MiniLM-L6-v2"],"evidence":"261 intervals / 503.79 ms vs 0 / 0.00 ms over 300 inferences","contested":false,"split":"train"}
{"id":"MEASURE-038","claim":"The longest single ANE interval in a Core ML trace, 361.41 ms, is the first-use ANE program load and compile rather than inference work.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-003-minilm-coreml-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","tracing","trap"],"entities":["xctrace","ane-hw-intervals"],"evidence":"excluding the 361.41 ms interval leaves 260 intervals totalling 142.38 ms","caveat":"that model on that machine; the load interval's size will vary with graph and cache state","contested":false,"split":"holdout"}
{"id":"MEASURE-039","claim":"Excluding the first-use load interval, the Core ML encoder consumed about 0.55 ms of ANE work per inference, roughly 75% of its 0.73 ms wall time.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-003-minilm-coreml-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","tracing"],"entities":["xctrace","ane-hw-intervals","all-MiniLM-L6-v2"],"evidence":"142.38 ms over 260 intervals","contested":false,"split":"train"}
{"id":"MEASURE-040","claim":"xctrace's ane-hw-intervals reported 0 intervals for a Core AI granite run using preferredComputeUnitKind neuralEngine while a Core ML control in the same session reported 269 intervals and 511.48 ms labelled Neural Engine Prediction.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-004-coreai-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","tracing","core-ai"],"entities":["xctrace","ane-hw-intervals","Core AI"],"evidence":"0 vs 269 intervals, same template and session","caveat":"Core AI on macOS 27.0, Xcode 27.0; may change in later releases","contested":false,"split":"train"}
{"id":"MEASURE-041","claim":"Even a system-wide xctrace capture with --all-processes reported 0 ANE intervals for Core AI against 1310 intervals and 1012.41 ms busy for a Core ML control, ruling out process scoping as the explanation.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-004-coreai-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","tracing","core-ai"],"entities":["xctrace","ane-hw-intervals","Core AI"],"evidence":"control mean interval 0.77 ms","contested":false,"split":"train"}
{"id":"MEASURE-042","claim":"A zero count of ane-hw-intervals means the instrument cannot see the runtime, not that the ANE was idle.","kind":"gotcha","confidence":"inferred","source":"/Volumes/data/local_ai_stack/results/EXP-004-coreai-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","tracing","trap"],"entities":["xctrace","ane-hw-intervals","Core AI"],"contested":false,"split":"train"}
{"id":"MEASURE-043","claim":"The ane-hw-intervals table is machine-wide, so attribution to a process is only valid when a clean control ran in the same capture window.","kind":"gotcha","confidence":"documented","source":"/Volumes/data/local_ai_stack/results/EXP-003-minilm-coreml-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","tracing","method"],"entities":["xctrace","ane-hw-intervals"],"contested":false,"split":"train"}
{"id":"MEASURE-044","claim":"The Core AI xctrace template exposes 36 tables, of which the Core AI-specific one is ODIEProfile with columns model-name, base-function-name, function-name, phase, category, color, level, activity and timing.","kind":"definition","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-004-coreai-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","tracing","core-ai"],"entities":["xctrace","Core AI","ODIEProfile"],"evidence":"9,127 ODIEProfile rows for a 22.8 s run","contested":false,"split":"train"}
{"id":"MEASURE-045","claim":"The ODIEProfile table carries no compute-unit or engine attribution: no per-op landed-on column and no per-engine lane exist in a Core AI trace.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-004-coreai-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","tracing","core-ai","limit"],"entities":["xctrace","Core AI","ODIEProfile"],"evidence":"observed category counts Inference 6080 / Setup 3043 / Load 4 and phase counts Inference 9123 / Load 4, all with function-name 'main'","contested":false,"split":"holdout"}
{"id":"MEASURE-046","claim":"The full xctrace template list on this machine is 25 entries and none of them is ANE-specific.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-004-coreai-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","tracing","limit"],"entities":["xctrace","Instruments"],"caveat":"Xcode 27.0 on macOS 27.0; template lists change between Xcode releases","contested":false,"split":"train"}
{"id":"MEASURE-047","claim":"metal-gpu-intervals attributes activity by process in a Core AI trace, making it the best in-trace signal for a Core AI run.","kind":"procedure","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-004-coreai-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","tracing","core-ai"],"entities":["xctrace","metal-gpu-intervals","Core AI"],"evidence":"54,846 Metal GPU intervals attributed to granite-runner, 61,920 command buffers, 113,172 gpu-state intervals, alongside 0 ane-hw-intervals","contested":false,"split":"train"}
{"id":"MEASURE-048","claim":"Instrument's Time Profiler answers which host code path ran by sampling the call tree under -[MLNeuralNetworkEngine predictionFromFeatures:], and an ANE run shows a call to -[_ANEClient evaluateWithModel...].","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/is-model-using-ane.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","profiling","placement"],"entities":["Instruments","Time Profiler","_ANEClient"],"contested":false,"split":"train"}
{"id":"MEASURE-049","claim":"Espresso logs per-op cost estimates under the [CostModelFeature] tag, and anemll-profile captures them by forking /usr/bin/log stream.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/anemll-profile/README.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","logging","cost-model"],"entities":["anemll-profile","Espresso","CostModelFeature"],"contested":false,"split":"train"}
{"id":"MEASURE-050","claim":"anemll-profile parses Espresso 'Unsupported op' compiler messages to report the specific reason a layer did not land on the ANE, such as 'Cannot support standalone slice_update' or 'Unsupported tensor data type: int32'.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/anemll-profile/README.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","logging","placement"],"entities":["anemll-profile","Espresso"],"contested":false,"split":"train"}
{"id":"MEASURE-051","claim":"Core ML and Espresso log streams are streamed on a Mac with the predicate '(subsystem IN {\"com.apple.espresso\",\"com.apple.coreml\"}) && (category IN {\"espresso\",\"coreml\"})' plus --info --debug.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/os-log.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","logging"],"entities":["log stream","Core ML","Espresso"],"contested":false,"split":"holdout"}
{"id":"MEASURE-052","claim":"Core ML and Espresso logs show <private> in place of model and layer names unless a device profile that exposes private data is installed.","kind":"gotcha","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/os-log.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","logging","trap"],"entities":["log stream","Core ML"],"contested":false,"split":"train"}
{"id":"MEASURE-053","claim":"Device logs can be retrieved with 'log collect --device --last 1d' and queried with 'log show --archive system_logs.logarchive --predicate ... --info --debug'.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/os-log.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","logging"],"entities":["log collect","log show"],"contested":false,"split":"train"}
{"id":"MEASURE-054","claim":"MLComputePlan is a public Core ML API that returns the compiler's per-op device assignment and cost weights for a model.","kind":"definition","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/ane-probe/README.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","mlcomputeplan"],"entities":["MLComputePlan","Core ML"],"contested":false,"split":"train"}
{"id":"MEASURE-055","claim":"ane-probe scans ANE op support by building a minimal single-op MIL program per op, converting it to an ML Program, compiling it, and querying MLComputePlan for device placement.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/ane-probe/README.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","mlcomputeplan","op-support"],"entities":["ane-probe","MLComputePlan"],"contested":false,"split":"train"}
{"id":"MEASURE-056","claim":"On this M4 with macOS 27.0 and coremltools 9.0, ane-probe scanned 168 MIL ops, built and queried 130 of them, and found 100 ANE-supported, i.e. 76.9% of the ops it could build.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-001-ane-op-map/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","mlcomputeplan","op-support"],"entities":["ane-probe","M4","coremltools"],"evidence":"168 scanned, 130 ok, 38 skipped, 100 ANE-supported","contested":false,"split":"train"}
{"id":"MEASURE-057","claim":"In the ane-probe M4 scan, only 1 of 168 rows reported preferred device ANE, because a single-op model pays ANE transfer overhead and the compiler therefore prefers CPU.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-001-ane-op-map/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","mlcomputeplan","trap"],"entities":["ane-probe","MLComputePlan"],"evidence":"preferred=ANE on 1 of 168 rows","contested":false,"split":"train"}
{"id":"MEASURE-058","claim":"The 'preferred' column of a single-op MLComputePlan query is meaningless, so only the 'supported' column should be read.","kind":"gotcha","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/ane-probe/README.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","mlcomputeplan","trap"],"entities":["ane-probe","MLComputePlan"],"contested":false,"split":"train"}
{"id":"MEASURE-059","claim":"Ops skipped by ane-probe are a probe limitation rather than evidence about what the ANE supports.","kind":"gotcha","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/ane-probe/README.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","mlcomputeplan","trap"],"entities":["ane-probe"],"contested":false,"split":"train"}
{"id":"MEASURE-060","claim":"MLComputePlan results reflect the compiler's static analysis, so actual runtime behaviour can differ with model context and input sizes.","kind":"gotcha","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/ane-probe/README.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","mlcomputeplan","limit"],"entities":["MLComputePlan","Core ML"],"contested":false,"split":"train"}
{"id":"MEASURE-061","claim":"MLComputePlan reports the per-op device support of a whole MIL op set but says nothing about where the hardware actually executed the model.","kind":"gotcha","confidence":"inferred","source":"/Volumes/data/local_ai_stack/repos/ane-probe/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","mlcomputeplan","limit"],"entities":["MLComputePlan"],"contested":false,"split":"train"}
{"id":"MEASURE-062","claim":"Calling MLComputePlan.load_from_path on an .mlpackage aborts the process with a C++ exception and takes buffered stdout with it.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/magenta-rt2-port.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","mlcomputeplan","trap"],"entities":["MLComputePlan"],"evidence":"advice recorded: flush or run it out-of-process","contested":false,"split":"train"}
{"id":"MEASURE-063","claim":"A hand-picked single-op ane-probe check reported conv as not ANE-supported while the full scan reported conv as ANE-supported, showing that spot checks can be artifacts of chosen parameters.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-001-ane-op-map/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","mlcomputeplan","trap"],"entities":["ane-probe"],"evidence":"ane_probe check conv -> ANE: NO; full scan -> conv ANE: YES","contested":false,"split":"train"}
{"id":"MEASURE-064","claim":"anemll-profile analyses the ordered MLComputePlan ops to find ANE graph interruption islands, ranking them by an estimated switch penalty plus island runtime, and tunes the boundary cost with --interrupt-ms and --interrupt-boundary-ms (300 ms by default).","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/anemll-profile/README.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","profiling","placement"],"entities":["anemll-profile","MLComputePlan"],"contested":false,"split":"holdout"}
{"id":"MEASURE-065","claim":"anemll-profile computes weight-only DRAM bandwidth, deliberately excluding L2-resident activations from the figure.","kind":"definition","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/anemll-profile/README.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","bandwidth"],"entities":["anemll-profile"],"contested":false,"split":"train"}
{"id":"MEASURE-066","claim":"Core AI ANE coverage can be counted statically with 'find <bundle>.aimodelc -name *ANE_region_*.mlir.bc | wc -l', where a count of 0 is the silent GPU fallback state.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/compute-units-and-authoring.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","region-count"],"entities":["coreai-build"],"contested":false,"split":"train"}
{"id":"MEASURE-067","claim":"coreai-build exits 0 with 0 ANE regions when the ANE compiler rejects a graph, so the exit code is not a placement signal.","kind":"gotcha","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/ane-quality-gate.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","region-count","trap"],"entities":["coreai-build"],"evidence":"4-bit group-8 palettization triggers this","contested":false,"split":"train"}
{"id":"MEASURE-068","claim":"Counting regions with the glob '*ANE_region*' double-counts every region because it matches both a directory and the file inside it, inflating a 13-region build to 14.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","region-count","trap"],"entities":["coreai-build"],"evidence":"corrected counts: fp16 v0 13 not 14; fp16 v1/v2/v3 1 not 2 (recorded as F-27)","contested":false,"split":"train"}
{"id":"MEASURE-069","claim":"ANE region count is a shape metric rather than a quality metric: one build at 13 regions and 122,832 interrupts and another at 1 region and 13,472 interrupts both moved about 88 GB, and the 1-region build was the faster one.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","region-count","performance"],"entities":["Core AI","granite-embedding-97m"],"evidence":"13 regions 13.19 ms vs 1 region 4.60 ms (recorded as F-26)","caveat":"M4/h16g, S=128, one graph","contested":false,"split":"train"}
{"id":"MEASURE-070","claim":"The number of ANE regions in a bundle equals the number of ANE submissions per inference at runtime: 25 regions measured statically produced 25.0 submissions per encoder pass, against 1 submission for a Core ML conversion.","kind":"fact","confidence":"measured","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/compute-units-and-authoring.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","region-count","dispatch"],"entities":["Core AI","Core ML","Parakeet FastConformer"],"evidence":"25.0 submissions of mean 5.906 ms vs 1.0 of 150.4 ms","contested":false,"split":"train"}
{"id":"MEASURE-071","claim":"Both the Core AI 25-submission route and the Core ML single-submission route give the ANE essentially the same work (147.6 ms vs 150.4 ms, within 2%), so the submission count changes delivery, not the amount computed.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/compute-units-and-authoring.md","source_type":"secondary","retrieved":"2026-09-23","topic":["instrumentation","dispatch","performance"],"entities":["Core AI","Core ML","Parakeet FastConformer"],"evidence":"ANE idle 28.7% across the window for Core AI vs 0.4% for Core ML; median inter-submission gap 1.125 ms vs 0.569 ms","contested":false,"split":"train"}
{"id":"MEASURE-072","claim":"coreai-build inspect prints the device's architecture, with h16g identifying M4 and h16c identifying M4 Max, so compiling for the wrong variant wastes a large build.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/results/EXP-004-coreai-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","build"],"entities":["coreai-build","h16g","h16c"],"evidence":"a 22-architecture compile is about 10 GB","contested":false,"split":"train"}
{"id":"MEASURE-073","claim":"There is no public API to ask at runtime which hardware Core ML is currently using for a model.","kind":"fact","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/is-model-using-ane.md","source_type":"secondary","retrieved":"2026-09-23","topic":["placement","limit"],"entities":["Core ML"],"contested":false,"split":"holdout"}
{"id":"MEASURE-074","claim":"A thread named H11ANEServicesThread visible when pausing the debugger means Core ML is using the Neural Engine for at least part of the model.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/is-model-using-ane.md","source_type":"secondary","retrieved":"2026-09-23","topic":["placement","debugger"],"entities":["Core ML","H11ANEServicesThread"],"contested":false,"split":"train"}
{"id":"MEASURE-075","claim":"A hit on the symbolic breakpoint -[_ANEModel program] means Core ML is using the ANE, but not necessarily for the whole model.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/is-model-using-ane.md","source_type":"secondary","retrieved":"2026-09-23","topic":["placement","debugger"],"entities":["_ANEModel","Core ML"],"caveat":"symbol names change between OS versions","contested":false,"split":"train"}
{"id":"MEASURE-076","claim":"Core ML's three Espresso engines are Espresso::ANERuntimeEngine for the ANE, Espresso::MPSEngine and Espresso::MetalLowmemEngine for the GPU, and Espresso::BNNSEngine for the CPU.","kind":"definition","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/is-model-using-ane.md","source_type":"secondary","retrieved":"2026-09-23","topic":["placement","debugger"],"entities":["Espresso","Core ML"],"contested":false,"split":"train"}
{"id":"MEASURE-077","claim":"GPU and CPU engine breakpoints include Espresso::MPSEngine::context::__launch_kernel, Espresso::BNNSEngine::convolution_kernel::__launch and Espresso::elementwise_kernel_cpu::__launch, with fallbacks Espresso::layer::__launch and Espresso::net::__forward.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/is-model-using-ane.md","source_type":"secondary","retrieved":"2026-09-23","topic":["placement","debugger"],"entities":["Espresso"],"contested":false,"split":"train"}
{"id":"MEASURE-078","claim":"Espresso symbols may change between iOS versions, so the live symbol set should be dumped with 'image dump symtab' after 'image list Espresso'.","kind":"gotcha","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/is-model-using-ane.md","source_type":"secondary","retrieved":"2026-09-23","topic":["placement","debugger","fragility"],"entities":["Espresso","lldb"],"contested":false,"split":"train"}
{"id":"MEASURE-079","claim":"Comparing model latency between computeUnits .all, .cpuAndGPU and .cpuOnly is a cheap placement signal: if .all is not much faster, Core ML may be using the ANE for only part of the model or not at all.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/is-model-using-ane.md","source_type":"secondary","retrieved":"2026-09-23","topic":["placement","method"],"entities":["MLModelConfiguration","Core ML"],"caveat":"a latency difference can also come from scheduling differences within one unit","contested":false,"split":"train"}
{"id":"MEASURE-080","claim":"SpecializationOptions preferredComputeUnitKind .cpu and .gpu declare the same allowedComputeUnitKinds of cpu, gpu and neuralEngine and differ only in which is preferred, and that preference is a partitioning input that can place a region on a different unit.","kind":"gotcha","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/compute-units-and-authoring.md","source_type":"secondary","retrieved":"2026-09-23","topic":["placement","trap"],"entities":["Core AI","SpecializationOptions"],"evidence":"blast radius runs from rounding-scale to anti-correlated across two unrelated models","contested":false,"split":"train"}
{"id":"MEASURE-081","claim":"cpu_only collapses the allowed compute-unit set to a single unit and is exact, so it is the right control for parity work rather than a preferred-unit setting.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/compute-units-and-authoring.md","source_type":"secondary","retrieved":"2026-09-23","topic":["placement","method"],"entities":["Core AI","cpu_only"],"contested":false,"split":"holdout"}
{"id":"MEASURE-082","claim":"A Core AI fp32 granite graph run with preferredComputeUnitKind neuralEngine executed on the GPU, shown by 0 ANE memory traffic, 0 ANE interrupts, 4421.6 mW of GPU power and 54,846 Metal GPU intervals.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-004-coreai-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["placement","core-ai"],"entities":["Core AI","granite-embedding-97m","M4"],"evidence":"four independent instruments agreed: power rails, Metal intervals, ANE intervals, IOReport traffic","contested":false,"split":"train"}
{"id":"MEASURE-083","claim":"A distinct, more deterministic latency profile is not evidence of a distinct execution unit: a Core AI neuralEngine arm at 4.331 ms with 0.015 ms spread against gpu at 4.982 ms with 0.461 ms spread were both executing on the GPU.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-004-coreai-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["placement","trap"],"entities":["Core AI","M4"],"evidence":"recorded as F-22; ranges did not overlap (4.320-4.335 vs 4.894-5.355)","contested":false,"split":"train"}
{"id":"MEASURE-084","claim":"The accelerator-contention differential method failed on this M4: a GPU-bound control slowed only 1.10x under a CPU+GPU hog, below the 1.15x threshold, so contention was not observable that way and every row of that matrix is void.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-004-coreai-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["placement","failed-method"],"entities":["M4","Core AI"],"contested":false,"split":"train"}
{"id":"MEASURE-085","claim":"Placement is a property of how a computation is expressed rather than of what it computes: arXiv 2608.22110 found a fused RMSNorm that is fully ANE-eligible while its arithmetically identical decomposition is CPU-only.","kind":"fact","confidence":"measured","source":"https://arxiv.org/abs/2608.22110","source_type":"primary","retrieved":"2026-09-23","topic":["placement","authoring"],"entities":["ANE","arXiv 2608.22110"],"caveat":"measured by the paper's authors with their own counters and models","contested":false,"split":"train"}
{"id":"MEASURE-086","claim":"Weight encoding gates ANE placement: arXiv 2608.22110 reports a 25.85M-parameter conv-heavy fp16 model assigned entirely to the CPU with zero bytes through the engine, while the same graph in int8 or 2-bit returned to about 83% residency and ran 1.8-2.2x faster.","kind":"measurement","confidence":"measured","source":"https://arxiv.org/abs/2608.22110","source_type":"primary","retrieved":"2026-09-23","topic":["placement","quantization"],"entities":["ANE","arXiv 2608.22110"],"evidence":"a separate 22.29M all-attention fp16 model sat at 98.9% residency","contested":false,"split":"train"}
{"id":"MEASURE-087","claim":"arXiv 2608.22110 establishes what actually ran by reading the ANE memory-controller byte counters during inference rather than trusting compiler intent.","kind":"procedure","confidence":"documented","source":"https://arxiv.org/abs/2608.22110","source_type":"primary","retrieved":"2026-09-23","topic":["placement","method"],"entities":["ANE","arXiv 2608.22110"],"contested":false,"split":"train"}
{"id":"MEASURE-088","claim":"arXiv 2608.22110 reports decode cost as bytes streamed per token at a constant ~0.77 fraction of nominal encoding width across fp16, int8 and 2-bit.","kind":"measurement","confidence":"measured","source":"https://arxiv.org/abs/2608.22110","source_type":"primary","retrieved":"2026-09-23","topic":["bandwidth","decode"],"entities":["ANE","arXiv 2608.22110"],"evidence":"constant ~0.77 fraction of nominal encoding width","contested":false,"split":"holdout"}
{"id":"MEASURE-089","claim":"Run-time compute-unit settings cannot override a Core AI AOT bundle: an fp16 bundle moved ANE bytes under both --compute neuralEngine and --compute gpu while --compute cpuOnly dropped to 0 interrupts.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["placement","core-ai","trap"],"entities":["Core AI","granite-embedding-97m"],"evidence":"101.6 GB under neuralEngine, 91.2 GB under gpu, 0 interrupts under cpuOnly","contested":false,"split":"train"}
{"id":"MEASURE-090","claim":"Effective ANE bandwidth should be computed as bytes moved divided by elapsed time, with bytes taken either from the IOReport AMC Stats counters or from weight bytes per token.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["bandwidth","method"],"entities":["enginemon","AMC Stats"],"contested":false,"split":"train"}
{"id":"MEASURE-091","claim":"The M4's ANE shows two throughput states differing by about 2.1x in both latency and effective bandwidth: a fast state at 1.85-2.25 ms and about 31 GB/s, and a slow state at about 4.75 ms and about 14.5 GB/s.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["throughput","latency","state"],"entities":["ANE","M4","granite-embedding-97m"],"evidence":"both figures move together by the same factor, the signature of a clock/throughput change rather than a data-location change","caveat":"M4/h16g, S=128, fp16, one graph","contested":false,"split":"train"}
{"id":"MEASURE-092","claim":"Within a single long ANE run the throughput transition is one-way: a 20,000-inference run had samples 0-830 in the fast state and samples 831-20,000 in the slow state with no flipping back.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["throughput","latency","state"],"entities":["ANE","M4"],"evidence":"19,169 consecutive slow samples","contested":false,"split":"train"}
{"id":"MEASURE-093","claim":"The ANE fast state is a burst condition rather than a per-run lottery: ten back-to-back bursts of 120 inferences were fast in 8 of 10, while a 1,200-inference run in the same period had a fast phase of only 258-385 samples.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["throughput","latency","state"],"entities":["ANE","M4"],"evidence":"burst latencies 2.13-2.25 ms","contested":false,"split":"holdout"}
{"id":"MEASURE-094","claim":"The ANE slow state does not recover with idle time: after 45 s of idle a run had 6 of 2,000 samples fast, and after 4 minutes it had 21 of 1,500.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["throughput","state"],"entities":["ANE","M4"],"contested":false,"split":"train"}
{"id":"MEASURE-095","claim":"Pre-loading the weights file into the OS page cache before an ANE run made the fast phase worse (385 to 258 fast samples), consistent with the ANE reading weights from unified memory regardless of file residency.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["throughput","state","memory"],"entities":["ANE","M4"],"evidence":"cat-ing the 186 MB resources.bin before the run dropped fast samples from 385 to 258","contested":false,"split":"train"}
{"id":"MEASURE-096","claim":"Repeating an identical ANE benchmark gave medians of 2.14, 2.15, 2.15, 2.17, 2.40, 3.38, 3.77, 4.26, 4.60 and 4.90 ms while the minimum stayed at 1.78-1.90 ms in every run.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["latency","method","statistics"],"entities":["ANE","M4","granite-embedding-97m"],"evidence":"a 4,000-iteration run is not enough to converge the median","contested":false,"split":"train"}
{"id":"MEASURE-097","claim":"A single-run ANE latency for a weight-streaming graph on this M4 carries up to a 2.1x spread, so min is the stable statistic and medians must be reported with their range.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["latency","method","statistics"],"entities":["ANE","M4"],"caveat":"demonstrated for one graph and one M4; other graphs may be stable","contested":false,"split":"train"}
{"id":"MEASURE-098","claim":"The ANE slow-tail cause remains unidentified after excluding thermals, page cache and an ANE-exclusive effect, with the leading candidates being ANE power/clock management with a long recovery constant or arbitration with another ANE client.","kind":"open-question","confidence":"inferred","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["throughput","state","open-question"],"entities":["ANE","M4"],"evidence":"pmset -g therm reported no thermal warning; the GPU shows the same burst shape; an idle 20 s enginemon monitor showed 0 B and 0 interrupts","contested":false,"split":"train"}
{"id":"MEASURE-099","claim":"On a thermally throttling phone, ANE 8-bit 1B decode dropped from 76 to about 52 tok/s at the fair-to-serious thermal transition roughly 70 s into a sustained run.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/ane-vs-gpu-iphone-2026-09.md","source_type":"our-own","retrieved":"2026-09-23","topic":["sustained","thermal","method"],"entities":["iPhone 17 Pro","MiniCPM5-1B"],"caveat":"wired USB with the screen on, which is itself a heater; an unplugged run may plateau higher","contested":false,"split":"train"}
{"id":"MEASURE-100","claim":"First-minute performance numbers are not sustained numbers on a phone.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/ane-vs-gpu-iphone-2026-09.md","source_type":"our-own","retrieved":"2026-09-23","topic":["sustained","thermal","method"],"entities":["iPhone 17 Pro"],"contested":false,"split":"train"}
{"id":"MEASURE-101","claim":"Speed A/B arms should be launched in the order A-B-A-B (or A-B-C-A-B-C for three arms) with about 20 s idle between launches and a fresh process per launch, reporting both rounds' values rather than one number.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/ane-vs-gpu-iphone-2026-09.md","source_type":"our-own","retrieved":"2026-09-23","topic":["method","thermal","protocol"],"entities":["iPhone 17 Pro"],"contested":false,"split":"train"}
{"id":"MEASURE-102","claim":"The sustained-measurement protocol idles each arm at least 3 minutes and until ProcessInfo.thermalState returns to fair or below, capped at 10 minutes, because a fixed 3-minute idle let the second arm start at serious.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/ane-vs-gpu-iphone-2026-09.md","source_type":"our-own","retrieved":"2026-09-23","topic":["method","thermal","protocol"],"entities":["ProcessInfo","iPhone 17 Pro"],"contested":false,"split":"train"}
{"id":"MEASURE-103","claim":"Equal-byte A/B comparisons must define weight bytes by the recipe rather than the file size, for example 8-bit k-means g32 against int8 per-block-32 both being 1 byte per weight.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/ane-vs-gpu-iphone-2026-09.md","source_type":"our-own","retrieved":"2026-09-23","topic":["method","quantization"],"entities":["Core AI","Core ML"],"contested":false,"split":"train"}
{"id":"MEASURE-104","claim":"On a locked phone screen the GPU is capped, so benchmark order must not be allowed to decide which arm looks faster.","kind":"gotcha","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/compute-units-and-authoring.md","source_type":"our-own","retrieved":"2026-09-23","topic":["method","trap"],"entities":["iPhone 17 Pro"],"contested":false,"split":"train"}
{"id":"MEASURE-105","claim":"Benchmarks must run serially: an overlapping palettization run inflated one sweep and every number in it had to be retaken.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/magenta-rt2-port.md","source_type":"our-own","retrieved":"2026-09-23","topic":["method","trap"],"entities":["Core AI"],"contested":false,"split":"train"}
{"id":"MEASURE-106","claim":"Cross-configuration speed claims on a phone need same-afternoon interleaved A/B testing rather than numbers from different days, because day-to-day noise was measured at about 1.4 tok/s.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/gemma4-raw-metal-a19-levers.md","source_type":"our-own","retrieved":"2026-09-23","topic":["method","noise"],"entities":["A19","Gemma 4"],"contested":false,"split":"holdout"}
{"id":"MEASURE-107","claim":"LiteRT's own fresh decode spread was plus or minus 6 tok/s within one afternoon on one device, so a single historical number is not decision-grade.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/raw-metal-loop-playbook.md","source_type":"secondary","retrieved":"2026-09-23","topic":["method","noise"],"entities":["LiteRT","iPhone 17 Pro"],"contested":false,"split":"train"}
{"id":"MEASURE-108","claim":"Per-kernel bandwidth probes on small tensors read cache-hot on A19 because the SLC swallows 5-10 MB tensors across repetitions, so only streams of about 100 MB or more give true DRAM numbers.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/gemma4-raw-metal-a19-levers.md","source_type":"our-own","retrieved":"2026-09-23","topic":["bandwidth","trap"],"entities":["A19","SLC"],"caveat":"A19 phone; cache sizes differ per chip","contested":false,"split":"train"}
{"id":"MEASURE-109","claim":"The audit rule before proposing kernel work is to compute effective GB/s as bytes-per-token divided by measured tok-s and compare it against what clean streams achieve on the same silicon.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/raw-metal-loop-playbook.md","source_type":"our-own","retrieved":"2026-09-23","topic":["bandwidth","method"],"entities":["A19"],"evidence":"A19 mixed/Gemma workloads achieve about 44 GB/s while clean int8 dense has measured into the 60s","contested":false,"split":"train"}
{"id":"MEASURE-110","claim":"An int8 Core AI decode core streaming 2.0 GB in 15.7 ms is about 127 GB/s, roughly 23% of the M4 Max peak of about 546 GB/s, which makes that path efficiency- or dispatch-bound rather than bandwidth-bound.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/performance-ceiling.md","source_type":"our-own","retrieved":"2026-09-23","topic":["bandwidth","analysis"],"entities":["M4 Max","Core AI","Gemma 4"],"evidence":"about 1000 Metal dispatches per token","caveat":"measured on a hand-rolled per-token loop, and Apple's pipelined engine runs the same weights about 3.5x faster","contested":false,"split":"train"}
{"id":"MEASURE-111","claim":"The M3 Neural Engine kernel DMA throttles DRAM weight streaming to 17-19 GB/s from a nominal 45-60 GB/s whenever the per-core transfer is an exact multiple of 1 MiB.","kind":"gotcha","confidence":"measured","source":"https://eiln.github.io/posts/ane-dma.html","source_type":"primary","retrieved":"2026-09-23","topic":["memory-bandwidth","dma","erratum"],"entities":["ANE","M3"],"evidence":"D=2048 at 997.6 us vs D=2016 at 293.8 us; nominal 45-60 GB/s falls to 17.3 GB/s","caveat":"M3 affected; M1 and M5 Max reportedly unaffected","contested":false,"split":"train"}
{"id":"MEASURE-112","claim":"At N=4096, the M3 ANE kernel DMA throughput was 16.93 GB/s at D=2048 against 44.51 GB/s at D=2016, a 27.57 GB/s or 62% collapse.","kind":"measurement","confidence":"measured","source":"https://eiln.github.io/posts/ane-dma.html","source_type":"primary","retrieved":"2026-09-23","topic":["memory-bandwidth","dma","measurement"],"entities":["ANE","M3"],"evidence":"44.505062 - 16.930761 = 27.574301 GB/s","caveat":"M3 Air, fanless, samples interleaved to equalise thermal ramp","contested":false,"split":"train"}
{"id":"MEASURE-113","claim":"The M3 ANE DMA bandwidth notch recovers to nominal within about 256 DMA lines, which is 16 KiB or one virtual-memory page, on either side of the boundary.","kind":"measurement","confidence":"measured","source":"https://eiln.github.io/posts/ane-dma.html","source_type":"primary","retrieved":"2026-09-23","topic":["memory-bandwidth","dma"],"entities":["ANE","M3"],"evidence":"64 B/line times 256 lines = 16 KiB = one page","contested":false,"split":"train"}
{"id":"MEASURE-114","claim":"Every k-th lap of the M3 ANE DMA notch collapses to the same bandwidth curve after recentering, with a ramp of 3.18 times k microseconds per line and R-squared of 0.96 to 0.99 per lap.","kind":"measurement","confidence":"measured","source":"https://eiln.github.io/posts/ane-dma.html","source_type":"primary","retrieved":"2026-09-23","topic":["memory-bandwidth","dma"],"entities":["ANE","M3"],"evidence":"one lap is 16 MiB at the 18 GB/s floor giving 900 us per lap","contested":false,"split":"holdout"}
{"id":"MEASURE-115","claim":"The M3 ANE DMA notch is not caused by core contention: streaming latency is constant from 1 to 16 active cores for both D=2016 and D=2048.","kind":"measurement","confidence":"measured","source":"https://eiln.github.io/posts/ane-dma.html","source_type":"primary","retrieved":"2026-09-23","topic":["memory-bandwidth","dma"],"entities":["ANE","M3"],"contested":false,"split":"train"}
{"id":"MEASURE-116","claim":"Randomly scrambling the weight fetch addresses across a 64 MiB IOVA arena did not explain the M3 ANE DMA collapse: baseline median throughput was 31.37 GB/s and scrambled was 32.29 GB/s.","kind":"measurement","confidence":"measured","source":"https://eiln.github.io/posts/ane-dma.html","source_type":"primary","retrieved":"2026-09-23","topic":["memory-bandwidth","dma","failed-hypothesis"],"entities":["ANE","M3"],"evidence":"scrambling explains about 1 GB/s of a roughly 200% effect; baseline and scrambled samples were interleaved run-to-run","contested":false,"split":"train"}
{"id":"MEASURE-117","claim":"The M3 LPDDR-6400 memory interface is 128 bit at 6.4 GT/s for 102.4 GB/s, which matches the advertised bandwidth of about 100 GB/s.","kind":"fact","confidence":"documented","source":"https://eiln.github.io/posts/ane-dma.html","source_type":"primary","retrieved":"2026-09-23","topic":["memory-bandwidth"],"entities":["M3","LPDDR-6400"],"contested":false,"split":"train"}
{"id":"MEASURE-118","claim":"Avoiding exact 1 MiB kernel transfers restored M3 ANE DMA bandwidth: splitting one 0x4000-line task into two 0x2000-line tasks raised throughput from 17.25 to 45.52 GB/s, a 2.66x gain.","kind":"procedure","confidence":"measured","source":"https://eiln.github.io/posts/ane-dma.html","source_type":"primary","retrieved":"2026-09-23","topic":["memory-bandwidth","dma","workaround"],"entities":["ANE","M3","ANEMLL"],"evidence":"four 0x1000-line tasks gave 44.83 GB/s, 2.60x","contested":false,"split":"holdout"}
{"id":"MEASURE-119","claim":"The M3 DMA workaround's null control holds: splitting a transfer that was not already a 1 MiB multiple (1 MiB minus 16 KiB) gave no speedup at all, proving the 2.6x gain comes from avoiding the prefetch bug.","kind":"measurement","confidence":"measured","source":"https://eiln.github.io/posts/ane-dma.html","source_type":"primary","retrieved":"2026-09-23","topic":["memory-bandwidth","dma","method"],"entities":["ANE","M3"],"contested":false,"split":"train"}
{"id":"MEASURE-120","claim":"Applying the M3 DMA workaround raised Llama 3.2 1B from 10.0 to 24.3 tokens/s and Qwen3-8B from 1.36 to 2.97 tokens/s.","kind":"measurement","confidence":"measured","source":"https://eiln.github.io/posts/ane-dma.html","source_type":"primary","retrieved":"2026-09-23","topic":["memory-bandwidth","dma","llm"],"entities":["ANE","M3","Llama 3.2 1B","Qwen3-8B","ANEMLL"],"evidence":"DRAM usage rose from 24.7 to 60.0 GB/s and 22.4 to 48.7 GB/s respectively","contested":false,"split":"train"}
{"id":"MEASURE-121","claim":"anemll states that the M3 ANE DMA erratum affects M3 but not M1 or M5 Max.","kind":"fact","confidence":"claimed","source":"https://news.ycombinator.com/item?id=49636479","source_type":"secondary","retrieved":"2026-09-23","topic":["memory-bandwidth","dma","scope"],"entities":["ANE","M1","M3","M5 Max","anemll"],"caveat":"a one-line project statement on a forum thread, not a published measurement","contested":false,"split":"train"}
{"id":"MEASURE-122","claim":"The M3 DMA study's measurement protocol used median microseconds per replica across three replicas, 40 runs, interleaved baseline and scrambled-address conditions to equalise thermal drift, and a register-file hexdiff to prove only the DMA size and address varied.","kind":"procedure","confidence":"measured","source":"https://eiln.github.io/posts/ane-dma.html","source_type":"primary","retrieved":"2026-09-23","topic":["method","memory-bandwidth","protocol"],"entities":["ANE","M3"],"evidence":"hexdiff of TD+0x078 core bases, TD+0x0b0-0x0f0 core sizes, TD+0x134 Common.Cin, TD+0x1f0 L2 source stride, TD+0x214 L2 result base","caveat":"40 runs and a single thermal/load session were the conditions the author states","contested":false,"split":"train"}
{"id":"MEASURE-123","claim":"The M3 DMA mechanism is proposed as a 14-bit prefetch-ring pointer whose distance arithmetic aliases one full lap remaining to empty, so an exactly 1 MiB transfer starves its own prefetch and runs on the slow no-speculation path.","kind":"open-question","confidence":"inferred","source":"https://eiln.github.io/posts/ane-dma.html","source_type":"primary","retrieved":"2026-09-23","topic":["memory-bandwidth","dma","mechanism"],"entities":["ANE","M3"],"evidence":"0x4000 lines = 1 MiB periodicity; the notch window equals 256 lines = one page","caveat":"the RTL shown is illustrative SystemVerilog written by the author, not leaked or decompiled source","contested":false,"split":"train"}
{"id":"MEASURE-124","claim":"A commenter on the M3 DMA write-up asked whether the SystemVerilog is a hypothesis rather than actual RTL, and no source-level confirmation has been published.","kind":"gotcha","confidence":"documented","source":"https://news.ycombinator.com/item?id=49636479","source_type":"secondary","retrieved":"2026-09-23","topic":["memory-bandwidth","dma","caveat"],"entities":["ANE","M3"],"contested":false,"split":"train"}
{"id":"MEASURE-125","claim":"The maderix/ANE project measures M4 ANE peak throughput at 18.6 TOPS fp16 and 35.1 TOPS int8 W8A8, a 1.88x ratio, using a 2048x2048 matmul in its inmem_peak benchmark.","kind":"measurement","confidence":"measured","source":"https://github.com/maderix/ANE","source_type":"primary","retrieved":"2026-09-23","topic":["throughput","peak","benchmark"],"entities":["maderix/ANE","ANE","M4"],"evidence":"128x conv 512ch 64x64: fp16 18.6 TOPS at 14.8 ms vs int8 35.1 TOPS at 7.8 ms","caveat":"private-API dispatch by the project's own harness; not independently reproduced by us","contested":false,"split":"train"}
{"id":"MEASURE-126","claim":"maderix/ANE reports that int8 activations halve L2 SRAM bandwidth between tiles via the MIL quantize and dequantize operations.","kind":"fact","confidence":"claimed","source":"https://github.com/maderix/ANE","source_type":"primary","retrieved":"2026-09-23","topic":["throughput","quantization","memory"],"entities":["maderix/ANE","ANE","M4"],"caveat":"mechanism explanation given by the project, not a counter-level measurement published by it","contested":false,"split":"train"}
{"id":"MEASURE-127","claim":"maderix/ANE states its ANE training utilisation is 5-9% of peak, with many element-wise operations still falling back to CPU.","kind":"measurement","confidence":"claimed","source":"https://github.com/maderix/ANE","source_type":"primary","retrieved":"2026-09-23","topic":["throughput","training","limit"],"entities":["maderix/ANE","ANE","M4"],"contested":false,"split":"holdout"}
{"id":"MEASURE-128","claim":"libane claims that implementing matmul as a 1x1 convolution gives a 3x throughput advantage over MIL matmul on the ANE, citing arXiv 2603.06728.","kind":"fact","confidence":"claimed","source":"https://github.com/AmiraniLabs/libane","source_type":"primary","retrieved":"2026-09-23","topic":["throughput","claim"],"entities":["libane","ANE"],"caveat":"project claim citing an external paper; we have not reproduced it","contested":false,"split":"train"}
{"id":"MEASURE-129","claim":"preferredComputeUnitKind neuralEngine produced a distinct latency profile from the gpu preference that nonetheless came from the GPU, showing that a latency signature cannot establish placement.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-004-coreai-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["placement","trap","latency"],"entities":["Core AI","M4"],"evidence":"recorded as F-22","contested":false,"split":"train"}
{"id":"MEASURE-130","claim":"A Core AI run's process-scoped trace recorded 54,846 Metal GPU intervals and 0 ANE intervals, giving a hardware-trace verdict on placement that does not depend on powermetrics being trustworthy.","kind":"procedure","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-004-coreai-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["placement","tracing","method"],"entities":["xctrace","metal-gpu-intervals","Core AI"],"evidence":"61,920 command buffers and 113,172 gpu-state intervals; background Metal rows attributed to other processes totalled a few hundred","contested":false,"split":"train"}
{"id":"MEASURE-131","claim":"Three independent instruments agreeing is the standard used before accepting an ANE placement verdict, because each fails differently: power rails, hardware intervals, and IOReport byte and interrupt counters.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/results/EXP-004-coreai-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["method","placement"],"entities":["powermetrics","xctrace","enginemon"],"contested":false,"split":"train"}
{"id":"MEASURE-132","claim":"The fixed latency protocol is 10 discarded warm-up calls then 100 measured calls back to back in one process, reporting p50, p95 and min with the work unit stated explicitly.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/bench/latency_protocol.py","source_type":"our-own","retrieved":"2026-09-23","topic":["method","latency","protocol"],"entities":["latency_protocol.py"],"contested":false,"split":"train"}
{"id":"MEASURE-133","claim":"ms/token is the only latency unit that means the same thing for an embedder, a decision model and a reranker, so it is the unit that can legitimately sit in a cross-class comparison table.","kind":"definition","confidence":"documented","source":"/Volumes/data/local_ai_stack/bench/latency_protocol.py","source_type":"our-own","retrieved":"2026-09-23","topic":["method","latency","unit"],"entities":["latency_protocol.py"],"contested":false,"split":"train"}
{"id":"MEASURE-134","claim":"A corpus of 142 latency figures had been measured under at least four different conventions with no stated warm-up and no normalisation, making the numbers real but not comparable.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/bench/latency_protocol.py","source_type":"our-own","retrieved":"2026-09-23","topic":["method","latency","comparability"],"entities":["latency_protocol.py"],"contested":false,"split":"train"}
{"id":"MEASURE-135","claim":"power_ab.py runs the same Core ML workload at ALL and CPU_ONLY, warm-ups 10 inferences, starts powermetrics with '--samplers ane_power,gpu_power,cpu_power -i 500', sleeps 2 s so the sampler settles, then loops predictions for the sampling window.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/bench/power_ab.py","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","method"],"entities":["power_ab.py","powermetrics"],"contested":false,"split":"train"}
{"id":"MEASURE-136","claim":"power_ab.py writes raw powermetrics logs as bench/power_ALL.txt and bench/power_CPU_ONLY.txt and derives per-rail mean, max and mJ per embedding from them.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/bench/power_ab.py","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","artifacts"],"entities":["power_ab.py"],"contested":false,"split":"train"}
{"id":"MEASURE-137","claim":"power_coreai.py runs the same Core AI graph once per compute-unit preference while sampling the power rails, and reads ANE rail high on neuralEngine with idle cpuOnly as proof the ANE ran it.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/bench/power_coreai.py","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","placement"],"entities":["power_coreai.py","Core AI"],"contested":false,"split":"train"}
{"id":"MEASURE-138","claim":"power_coreai.py's stated fallback readings are: GPU rail high on neuralEngine means the preference fell back to the GPU, and neither rail moving means CPU fallback.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/bench/power_coreai.py","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","placement"],"entities":["power_coreai.py","Core AI"],"contested":false,"split":"train"}
{"id":"MEASURE-139","claim":"power_coreai.py sleeps 2 s after starting the powermetrics sampler so it settles before the workload starts, and writes raw logs per compute-unit arm.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/bench/power_coreai.py","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","method"],"entities":["power_coreai.py","powermetrics"],"contested":false,"split":"train"}
{"id":"MEASURE-140","claim":"power_coreai.py and the phase probe both reuse power_ab.parse_power so that the same raw powermetrics output is parsed identically by every power tool.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/bench/power_coreai.py","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","method"],"entities":["power_coreai.py","power_ab.py"],"contested":false,"split":"train"}
{"id":"MEASURE-141","claim":"A phase-probe run's anomalous reading of 0-14 mW ANE power and CPU up to 6.6 W was caused by a parser bug that silently dropped most powermetrics samples, parsing 14 where about 51 were expected.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["instrumentation","power","trap"],"entities":["powermetrics","power_phase_probe.py"],"evidence":"recorded as F-29; the real CPU figure was about 1 W","contested":false,"split":"train"}
{"id":"MEASURE-142","claim":"The fix for the power-parser bug was threefold: use the single validated parser, write the raw log so any disagreement is checkable, and refuse to print a verdict when either window has fewer than 3 samples.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["method","power","protocol"],"entities":["powermetrics"],"contested":false,"split":"holdout"}
{"id":"MEASURE-143","claim":"A probe that printed a verdict with n=1 in one window after the run never entered the state being probed is the same failure family as a probe whose parser dropped most samples.","kind":"gotcha","confidence":"inferred","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["method","trap","statistics"],"entities":["power_phase_probe.py"],"evidence":"recorded as F-28 and F-29","contested":false,"split":"train"}
{"id":"MEASURE-144","claim":"A tool that answers when it should stay silent is the mechanism by which confident wrong ANE results get published.","kind":"gotcha","confidence":"inferred","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["method","trap"],"entities":["power_phase_probe.py","enginemon"],"contested":false,"split":"train"}
{"id":"MEASURE-145","claim":"A negative or failed method should be recorded rather than discarded, because the void contention matrix and the n=1 probe are as instructive as the successful runs.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/results/EXP-004-coreai-ane/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["method","record-keeping"],"entities":["EXP-004","EXP-005"],"contested":false,"split":"holdout"}
{"id":"MEASURE-146","claim":"A measurement run should record OS build, toolchain version, chip architecture, model or bundle identifier, sequence length, dtype or quantisation recipe, and machine power state, because numbers from different builds are not comparable.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/ane-vs-gpu-iphone-2026-09.md","source_type":"our-own","retrieved":"2026-09-23","topic":["method","protocol","metadata"],"entities":["coreai-build"],"evidence":"a mid-session phone OS update colded every specialization cache and nothing was compared across the two builds","contested":false,"split":"train"}
{"id":"MEASURE-147","claim":"A positive control that is known to use the ANE and a negative control that cannot must be run on the target machine and OS before any ANE number from a new instrument is believed.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["method","protocol","controls"],"entities":["enginemon","Core ML"],"contested":false,"split":"train"}
{"id":"MEASURE-148","claim":"The count of ANE regions should be checked after every Core AI AOT compile because that count is the only file-level evidence of ANE coverage.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/ane-quality-gate.md","source_type":"secondary","retrieved":"2026-09-23","topic":["method","region-count"],"entities":["coreai-build"],"contested":false,"split":"train"}
{"id":"MEASURE-149","claim":"A throughput claim for a cross-runtime comparison should be backed by a same-toolchain control export, so that a bundle built by an older toolchain is not attributed to the runtime.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/ane-vs-gpu-iphone-2026-09.md","source_type":"our-own","retrieved":"2026-09-23","topic":["method","protocol","controls"],"entities":["coreai-build","coreai-torch"],"contested":false,"split":"train"}
{"id":"MEASURE-150","claim":"The ANE's differentiated value in our measurements is energy and load time rather than sustained throughput, because the same bundle forced onto the GPU drew 4124 mW where the ANE path drew 75 mW of GPU power but ran only moderately faster in steady state.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["power","efficiency","conclusion"],"entities":["ANE","granite-embedding-97m","M4"],"evidence":"ANE-resident path at 4.60 ms median against 5.52 ms for the same bundle on GPU, with residual GPU power 75 mW vs 4124 mW","caveat":"M4/h16g, S=128, fp16, one graph; sustained parity is the measured state, not a win","contested":false,"split":"train"}
{"id":"MEASURE-151","claim":"The xctrace 'Core AI' template on M5 Max / macOS 27 (26A434) instantiates but starves unprivileged: list shows 25 standard templates incl. Core AI and Foundation Models; record --template 'Core AI' --launch produces a 1.8 MB trace whose TOC carries ODIEProfile, mps-hw-intervals, metal-shader-profiler, os-signpost, time-profile and 21 kdebug tables, yet every Core AI/Metal table exports ZERO rows because the run aborts with 'Failed to start the recording: Could not set the recording priority' — the Core AI row streams need elevated privilege here, refining MEASURE-043 (time-profile-style templates do work unprivileged).","kind":"measurement","confidence":"measured","source":"results/EXP-028-apple-tracer/results/e2_xctrace_coreai.txt","source_type":"our-own","retrieved":"2026-10-08","topic":["tooling","odie","privilege"], "entities":["xctrace","Core AI template","ODIEProfile","mps-hw-intervals"], "evidence":"p28_e2b.trace TOC + header-only table XMLs archived in raw/p28_e2/; exact one-shot sudo command recorded for row-side completion","caveat":"Xcode 27-specific; row-side parity with the M4 36-table record stays open until a user sudo run","contested":false, "split":"train"}
```

---

## Sources

Local sources read for this file.

| path | what it gave |
| --- | --- |
| `/Volumes/data/local_ai_stack/knowledge/ane/00-DESIGN.md` | the record schema, confidence and split rules |
| `/Volumes/data/local_ai_stack/tools/enginemon/README.md` | enginemon's purpose, invocation, control table, scope caveats (our own; no licence file in the directory — unlicensed internal work) |
| `/Volumes/data/local_ai_stack/tools/enginemon/enginemon.c` | group merging, delta sampling, the `TRIG` exclusion, the frozen-channel label, the summary definition (our own) |
| `/Volumes/data/local_ai_stack/results/EXP-001-ane-op-map/README.md` | M4 op-support scan, the `preferred`-is-meaningless and spot-check corrections (our own) |
| `/Volumes/data/local_ai_stack/repos/ane-probe/README.md` | MLComputePlan scanning method, limitations (repo `LICENSE` present; upstream `xrl1/ANE-probe`) |
| `/Volumes/data/local_ai_stack/repos/ane-probe/results/M4/macOS_27.0/coremltools_v9.0/ane_support_results.csv` | the 168-row M4 scan; counted 1 `preferred=ANE` row directly |
| `/Volumes/data/local_ai_stack/results/EXP-003-minilm-coreml-ane/README.md` | `ane-hw-intervals` positive/negative pair, first-load interval, ANE power and energy-per-embedding (our own) |
| `/Volumes/data/local_ai_stack/results/EXP-004-coreai-ane/README.md` | the four-instrument Core AI placement verdict, Metal intervals, ODIEProfile columns, template list, F-22, the void contention method (our own) |
| `/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md` | region-count corrections F-26/F-27, burst/sustained characterisation, the 200× power disagreement and F-28/F-29, F-26 (our own) |
| `/Volumes/data/local_ai_stack/results/RESEARCH-SWEEP.md` | pointers to the DMA erratum, arXiv 2608.22110, maderix/ANE numbers (our own compilation) |
| `/Volumes/data/local_ai_stack/bench/ane_report.py` | the `ane-hw-intervals` export path and summariser (our own) |
| `/Volumes/data/local_ai_stack/bench/power_ab.py` | powermetrics A/B method, raw-log rule (our own) |
| `/Volumes/data/local_ai_stack/bench/power_coreai.py` | per-compute-unit power A/B and its interpretation rules (our own) |
| `/Volumes/data/local_ai_stack/bench/latency_protocol.py` | the fixed latency protocol and why it exists (our own) |
| `/Volumes/data/local_ai_stack/bench/probe_ane_regions.py` | region-count probe, `coreai-build` path, artefacts-outside-bench rule (our own) |
| `/Volumes/data/local_ai_stack/repos/aneperf/README.md` | IOReport group inventory, PMP states, derived utilisation, private-API caveat (repo `LICENSE` present; upstream `tmc/aneperf`) |
| `/Volumes/data/local_ai_stack/repos/anemll-profile/README.md` | Espresso `[CostModelFeature]` capture, interruption islands, weight-only bandwidth (declared **MIT**) |
| `/Volumes/data/local_ai_stack/repos/neural-engine/docs/is-model-using-ane.md` | H11ANEServicesThread, breakpoints, Espresso engine symbols, Time Profiler, powermetrics (repo is the `hollance/neural-engine` community reference; check its `LICENSE` before redistribution) |
| `/Volumes/data/local_ai_stack/repos/neural-engine/docs/os-log.md` | os_log / `log stream` predicates and the `<private>` limitation |
| `/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/compute-units-and-authoring.md` | submission-count = region-count finding, `preferredComputeUnitKind` hazard, `cpu_only()` (zoo knowledge base; licence not verified here — read as a source, not redistributed) |
| `/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/ane-quality-gate.md` | exit-code-0-with-0-regions, count-regions-after-every-AOT rule |
| `/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/ane-vs-gpu-iphone-2026-09.md` | interleaved A/B protocol, thermal-recovery protocol, equal-byte definition, sustained curves |
| `/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/performance-ceiling.md` | 127 GB/s vs 546 GB/s dispatch-bound calculation; AOT-not-throughput caveat |
| `/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/raw-metal-loop-playbook.md` | LiteRT ±6 tok/s spread; audit-before-proposing GB/s rule |
| `/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/magenta-rt2-port.md` | serial-benchmark rule; `MLComputePlan.load_from_path` abort; count-residency rule |
| `/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/gemma4-raw-metal-a19-levers.md` | ±1.4 tok/s day noise; SLC cache-hot small-tensor probes |

External sources, with declared licence where one exists.

| source | licence / terms | how used |
| --- | --- | --- |
| https://eiln.github.io/posts/ane-dma.html | no licence declared; blog post, copyright the author | measured facts about the M3 DMA erratum and the structure of its measurement protocol; no verbatim prose |
| https://news.ycombinator.com/item?id=49636479 | HN content, copyright contributors | the M1/M5 Max-unaffected claim and the "is this actual RTL?" caveat |
| https://arxiv.org/abs/2608.22110 | arXiv; check the paper's own licence | placement-as-expression, weight-encoding-gates-placement, bytes-per-token 0.77 fraction, byte-counter method |
| https://arxiv.org/abs/2606.22283 | arXiv; check the paper's own licence | the ANE architecture/programming/performance reference, including its measured/decompiled/predicted labelling discipline |
| https://github.com/maderix/ANE | **MIT** (stated in README) | peak TOPS fp16/int8 W8A8, SRAM/`inmem` benchmark inventory, 5-9% training utilisation |
| https://github.com/AmiraniLabs/libane | **Apache-2.0** (stated in README) | the conv1×1-vs-MIL-matmul 3× claim (cited to arXiv 2603.06728) |

Unreachable or not attempted, stated rather than dropped: we did not fetch the `tinygrad/extra/accel/ane` sources, the `iokit`/`IOSurface` headers from `nst/iOS-Runtime-Headers`, the `anemll`, `ane-infer`, `ane.cpp` or `qwen-ane-llm` repositories, or the Apple machine-learning research index; none of them was needed for a claim made here, and none is cited. The `coreai-model-zoo`, `neural-engine` and `ane-probe` repositories are read as local checkouts; their licence files were not opened for this file, so no redistribution claim is made for their prose.