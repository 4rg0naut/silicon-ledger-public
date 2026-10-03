# EXP-004 — Core AI on the ANE (Apple's new runtime, base M4)

**Questions:** does Apple's *new* Core AI runtime work on a base M4? Can a real model be put
on the Neural Engine through it? The zoo card for this model lists **"the Neural Engine"**
under *Not tested*, and its Mac numbers were **GPU-preferred**.

**Run:** 2026-09-20 · macOS 27.0 (26A428) · Xcode 27.0 (27A266a) · coreai-kit **0.4.2**

---

## Step 1 — Core AI works on the base M4 ✅

```bash
cd repos/coreai-kit && git checkout 0.4.2
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
swift run -c release --package-path Examples/ChatDemo chat-cli \
  --model qwen3-0.6b --prompt "What is the capital of Japan?"
```
Swift build 62.4 s from clean · model ~352 MB · total 109.8 s · exit 0 · **correct answer**
(*"The capital of Japan is Tokyo…"*). Core AI + the community kit are functional on a base M4.

## Step 2 — Granite-Embedding-97M: gates pass on every placement; **ANE not used**

**Harness:** `tools/granite-runner` (Swift, depends on the local coreai-kit 0.4.2). It runs
two gates and a latency loop:
1. **Tokenizer parity** — our encoding must equal the reference `input_ids`/`attention_mask`.
2. **Numeric parity** — embedding cosine vs the HF oracle in `reference.json`.
   *Not optional:* Core AI compute-unit settings are **preferences** over the allowed set, and
   the kit documents a placement defect that "returns silently wrong numerics on some graphs".

```bash
BIN=tools/granite-runner/.build/out/Products/Release/granite-runner
B=models/granite97m/macos/fp32-s128
"$BIN" "$B/granite97m_fp32_s128_bound.aimodel" "$B/tokenizer" "$B/reference.json" \
      --compute neuralEngine --iters 105
```

### Results — all four placements (base M4, S=128, fp32, 105 warm samples)

| compute | load | first after load | **warm median** | vs cpuOnly | gate |
| --- | ---: | ---: | ---: | ---: | --- |
| `cpuOnly` | 594 ms | 19.58 ms | 8.28 ms | — | **PASS** (cos 0.999999940) |
| `cpu` (preference) | 392 ms | 15.21 ms | 8.28 ms | 1.00× | PASS (cos 0.999999940) |
| `gpu` | 510 ms | **741.21 ms** | 6.06 ms | 1.37× | PASS (cos 0.999999881) |
| **`neuralEngine`** | 474 ms | 21.24 ms | **4.33 ms** | **1.91×** | PASS (cos 0.999999881) |

- **Tokenizer: 35/35 exact on every run.** Numeric gate: max \|err\| 2.98e-07, **0/35 failures**.
- The documented "silently wrong numerics" defect **did not manifest** on this graph — it is
  graph-specific, as the kit says.
- `.gpu` has a pathological **first-after-load cost of 741 ms** (vs 21 ms for the ANE
  preference, 20 ms CPU) — worth knowing for cold-start-sensitive use.
- Our base-M4 `neuralEngine` number (**4.33 ms**) is close to the published **M4 Max
  GPU-preferred 4.14 ms** — a base M4 with the ANE preference nearly matches an M4 Max on GPU.

### The ANE claim: four probes, and only the last one can see the ANE

The `neuralEngine` preference is **1.91× faster than CPU-only and numerically correct**, so
work *is* being offloaded. But "offloaded" is not "on the ANE", and `preferredComputeUnitKind`
is documented as a *preference*, not a guarantee. Four probes, in increasing rigour:

**1. Process-scoped `xctrace` — blind.**

| Run | `ane-hw-intervals` |
| --- | --- |
| Granite `neuralEngine` | 0 |
| Granite `cpuOnly` (control) | 0 |
| **MiniLM Core ML `ALL`** (control, same template/session) | **269**, 511.48 ms, *Neural Engine Prediction* |

**2. System-wide `xctrace` — still blind** (`bench/syswide_ane.py`; `--all-processes`, so
out-of-process ANE dispatch would also be captured):

| arm | ANE intervals | expectation |
| --- | ---: | --- |
| MiniLM Core ML `ALL` | **1310** (1012.41 ms busy, mean 0.77 ms) | positive — ✅ capture works |
| MiniLM Core ML `CPU_AND_GPU` | 0 | negative — ✅ clean |
| Granite `cpuOnly` | 0 | negative — ✅ clean |
| **Granite `neuralEngine`** | **0** | the question |

This rules out process-scoping as the explanation: with a *working* system-wide positive
control in the same session, a Core AI `.neuralEngine` run registers **no ANE hardware
activity at all**.

**3. Accelerator contention — method failed, result void** (`bench/interference_coreai.py`).
The idea: an ANE-saturating Core ML hog (`ALL`) must slow an ANE-bound process, while a hog
that *cannot* touch the ANE (`CPU_AND_GPU`) must not. The positive control killed it —
`granite(gpu)` slowed only **1.10×** under a CPU+GPU hog, below the 1.15× threshold, so
contention is not observable this way on this machine. **Every row of that matrix is void**;
the script reports the failure rather than a false verdict. Recorded as a failed method.

### What the latency signature says (5 rounds × 1200 warm inferences)

| compute | median | spread over 5 runs | gate |
| --- | ---: | ---: | --- |
| `neuralEngine` | **4.331 ms** | **0.015 ms** | PASS |
| `gpu` | 4.982 ms | 0.461 ms | PASS |
| `cpuOnly` | 8.164 ms | 0.109 ms | PASS |

`neuralEngine` and `gpu` ranges **do not overlap** (4.320–4.335 vs 4.894–5.355), and
`neuralEngine` is **~30× more deterministic** than `gpu` — a distinct execution profile.
⚠️ **This signature was misleading** (see the verdict below): it looks like a separate
hardware unit, but it is a different **GPU schedule**, not a different accelerator. Recorded
as **F-22** — a distinct latency profile is not evidence of a distinct execution unit.

### ✅ DECISIVE — power rails: the ANE preference **falls back to the GPU**

Root required (`xctrace`'s Power Profiler template is *"not supported on macOS"*).
`bench/power_coreai.py`, 3000 inferences per arm, sampling `ane_power,gpu_power,cpu_power`:

```bash
cd /Volumes/data/local_ai_stack && sudo .venv/bin/python bench/power_coreai.py --iters 3000
```

| compute | gate | median | **ANE mW** | **GPU mW** | CPU mW |
| --- | --- | ---: | ---: | ---: | ---: |
| **`neuralEngine`** | PASS | 4.30 ms | **0.0** | **4421.6** | 3228.8 |
| `gpu` | PASS | 5.55 ms | **0.0** | 3407.6 | 2201.6 |
| `cpuOnly` | PASS | 8.04 ms | **0.0** | 0.3 | 6085.2 |

**Sampler validity** — same sampler, same machine, same day (EXP-003's Core ML control):
`ALL` → ANE **2463.0 mW mean, 3399 mW peak**; `CPU_ONLY` → ANE 6.0 mW. The rail reads the
ANE perfectly well.

**The GPU rail tracks our workload exactly**: 0.3 mW (`cpuOnly`) → 3407.6 mW (`gpu`) →
4421.6 mW (`neuralEngine`). So the GPU did the work in the `neuralEngine` arm.

**Two independent readings, same conclusion:**
1. ANE draw is **0 mW in every arm and every sample** — not even the 6–10 mW idle floor that
   the Core ML control shows. The ANE was fully power-gated: it was never touched.
2. The GPU burned **4.4 W** during the `neuralEngine` run — *more* than the explicit `gpu`
   arm — while CPU draw also rose (3228.8 vs 2201.6 mW).

**Verdict: `preferredComputeUnitKind: .neuralEngine` does NOT put this graph on the Neural
Engine on a base M4. It executes on the GPU** — via a different, more aggressive schedule
(hence faster than the `.gpu` preference *and* more power-hungry). The card's *"Not tested:
the Neural Engine"* is therefore answered **negatively** for this configuration.

**Mechanistic hypothesis for the fallback (testable):** the bundle's metadata reads
`"Portable source IR, no AOT."` An ANE path plausibly requires an **AOT-compiled** asset; a
portable JIT bundle may have no ANE target to select, so the preference degrades to GPU. Next
experiment: AOT-compile the same graph and re-run this exact power A/B. If ANE draw appears,
the fallback is a *build-mode* consequence, not a runtime defect.

### ✅ Confirmed by a second, non-power instrument: Metal

Same `Core AI` template trace, `--compute neuralEngine`, 22.8 s, target exit 0:

| table | rows |
| --- | ---: |
| `metal-gpu-intervals` — attributed to **`granite-runner (27588)`** | **54,846** |
| `metal-command-buffer-completed` | 61,920 |
| `metal-gpu-state-intervals` | 113,172 |
| **`ane-hw-intervals`** | **0** |

The process drove **54,846 Metal GPU intervals** while registering **zero** ANE intervals.
This is hardware-instrument evidence, independent of power sampling, so the verdict does not
rest on `powermetrics` being trustworthy. (Metal rows attributed to other processes in the same
window: Brave helper 655, Terminal 566, WindowServer 550 — i.e. background, not ours.)

### ✅ Fourth instrument: our own unprivileged IOReport monitor (`tools/enginemon`)

`powermetrics` needs root and `xctrace` is blind to Core AI, so we built the missing
instrument: a single-file C tool that reads Apple's private **IOReport** counters directly.
An unprivileged process can list, subscribe to and sample them (verified: euid 501).

```bash
clang -O2 -o enginemon tools/enginemon/enginemon.c -framework CoreFoundation
tools/enginemon/enginemon --interval 500 --duration 25 -- \
  tools/granite-runner/.build/out/Products/Release/granite-runner \
  models/granite97m/macos/fp32-s128/granite97m_fp32_s128_bound.aimodel \
  models/granite97m/macos/fp32-s128/tokenizer \
  models/granite97m/macos/fp32-s128/reference.json --compute neuralEngine --iters 3000
```

| counter | granite `.neuralEngine` | granite `.gpu` | Core ML `ALL` (control) |
| --- | ---: | ---: | ---: |
| `AMC Stats → ANE DCS RD` (bytes) | **0** | 0 | **128–171 GB** |
| `AMC Stats → ANE NRT AF RD` | **0** | 0 | 184 GB |
| `PMP → ANE0 RD` (events) | **0** | 0 | 29,252 |
| `ane 0` interrupts | **0** | 0 | 24,538–37,368 |
| `Energy Model → GPU Energy` | **6173 mW** | 3101 mW | ~14 mW |

Zero ANE memory traffic, zero ANE interrupts, zero ANE PMP events — while the GPU drew 6.2 W.
The **same tool, same session** reports 171 GB and 24,538 interrupts for the Core ML control,
so the zeros are real, not a broken probe.

**Two traps this tool documents** (both nearly produced confident wrong answers):
`Energy Model → ANE` is a **frozen** counter (constant under idle *and* under a known-ANE
workload) — reporting its zero would fabricate a negative; and `SoC Stats → ANE_*_TRIG` is a
**free-running 24 MHz clock** that advances by `elapsed × 24e6` regardless of load. Both are
excluded/labelled. See `tools/enginemon/README.md`.

**Verdict now rests on four independent instruments**: power rails (`powermetrics`), Metal
GPU intervals (`xctrace`), ANE intervals (`xctrace`, process-scoped *and* system-wide), and
IOReport ANE traffic/interrupts (`enginemon`, unprivileged). All four agree.

### ✅ The AOT question — ANSWERED (and the hypothesis was wrong)

**Setup.** The Metal Toolchain was missing (`aimodelc` refused: *"Core AI requires the Metal
Toolchain"*). Installed it with `xcodebuild -downloadComponent MetalToolchain` (838.9 MB,
`com.apple.dt.toolchain.Metal.32023.921.5`). It contains **`coreai-build 3600.83.1`** — the exact
tool and version the zoo's recipe calls — at
`…/Metal.xctoolchain/usr/bin/coreai-build`.

```bash
coreai-build compile granite97m_fp32_s128_bound.aimodel --output aot-ane \
    --platform macOS --preferred-compute neural-engine     # 22 architectures, 21 s
coreai-build inspect <bundle>.aimodelc                     # tells you YOUR architecture
```

**The compiled bundle loads and passes the gate — but it still runs on the GPU.**

| | JIT `.aimodel` | AOT `.aimodelc` (neural-engine) |
| --- | ---: | ---: |
| ANE memory traffic | 0 B | **0 B** |
| ANE interrupts | 0 | **0** |
| GPU power | 6173 mW | **10,707.9 mW** |
| gate | PASS | PASS — 35/35, cos 0.999999881, **4.312 ms** |

**The compile-time flag changed nothing about the target:**

| build | ANE regions | delegates emitted |
| --- | ---: | --- |
| `--preferred-compute neural-engine`, macOS h16g | **0** | MPSGraph only |
| `--preferred-compute gpu`, macOS h16g | **0** | MPSGraph only |
| `--preferred-compute neural-engine`, **iOS h18p** | **0** | MPSGraph only |

The zoo's own guard names this exact state (`apps/AneGate/_ane_export_s1.py`):

```bash
find <bundle>.aimodelc -name '*ANE_region*' | wc -l   # 0 = "silent GPU fallback — not an ANE arm"
```

**So "it's a packaging problem" is falsified — the cause is authoring.** The zoo's
`knowledge/compute-units-and-authoring.md` states the ANE recipe:

> **iOS/ANE = static-shape, BC1S, Conv2d, per-head, fp16-only**

This graph is **fp32**, in **standard `(B,S,D)` layout**, with **`nn.Linear` projections** — it
violates the ANE recipe on dtype, layout *and* projection form. No compute-unit preference —
JIT or AOT, macOS or iOS — can place it on the ANE. Every ANE bundle in the zoo (31/31 regions)
was *authored* to that recipe, and **no macOS bundle in the zoo has ever had ANE regions**.

**Practical notes for reuse:**
- `coreai-build inspect` prints `This device's architecture`. Ours is **h16g**; `h16c` is
  M4 **Max** — picking the wrong variant wastes a 10 GB compile.
- A 22-architecture compile is ~10 GB; pass `--architecture <yours>` unless you need all.
- `aimodelc` (the `xcrun` front end) still refuses with "requires the Metal Toolchain" even
  after installation, because it resolves toolchains through Xcode's `Toolchains/` directory
  and the cryptex lives outside it. **Call `coreai-build` from the toolchain directly.**

### What the `Core AI` instrument actually contains — and what it does not

A `Core AI` trace exposes **36 tables**. The Core AI-specific one is **`ODIEProfile`**
(9,127 rows for this run). Its columns are `model-name`, `base-function-name`, `function-name`,
`phase`, `category`, `color`, `level`, `activity`, and timing. Observed values:

| column | values |
| --- | --- |
| `category` | Inference 6080, Setup 3043, Load 4 |
| `phase` | Inference 9123, Load 4 |
| `color` | Blue 6080, Purple 3043, Teal 4 |
| `function-name` | `main` (all 9,125) |
| `model-name` | `granite97m_fp32_s128_bound` |

**There is no compute-unit or engine attribution anywhere** — no per-op "landed on X" column,
and no per-engine lane. Nor is there a separate Neural Engine instrument: the full template list
is 25 entries (Activity Monitor … Core AI, CPU Counters, CPU Profiler, Foundation Models, Metal
System Trace, Power Profiler, Processor Trace, System Trace, Time Profiler …), **none ANE-specific**.

So the practical answer to "how do I see which engine my Core AI graph used?" is: **you cannot,
from xctrace.** `ane-hw-intervals` is blind to Core AI, `ODIEProfile` carries no placement, and
there is no ANE template. `metal-gpu-intervals` *does* attribute by process and is the best
in-trace signal; power rails remain the only direct ANE measurement.

## Artifacts
- `bench/chatcli_qwen3_06b.log` — step-1 build/download/run
- `tools/granite-runner/` — the harness (vendored tokenizer + gates + latency)
- `models/granite97m/` — bundle (378 MB JIT `.aimodel`), pinned tokenizer, `reference.json` (35 fixtures)
- `bench/syswide_ane.py` — system-wide ANE capture with positive + negative controls
- `bench/interference_coreai.py` — accelerator-contention differential (**method failed**, kept for the record)
- `bench/power_coreai.py` — the power-rail A/B (needs sudo; **the decisive test**)
- `results/EXP-004-coreai-ane/raw/power_{neuralEngine,gpu,cpuOnly}.txt` — the raw `powermetrics` logs behind the verdict
- `bench/ane_report.py` — `ane-hw-intervals` summariser
- `tools/enginemon/` — our own **unprivileged** per-engine monitor (IOReport); the fourth instrument, with its own README documenting the frozen-channel and free-running-clock traps
- `models/granite97m/macos/fp32-s128/aot-ane/granite97m_fp32_s128_bound.h16g.aimodelc` (480 MB) — AOT-compiled with `--preferred-compute neural-engine`; **0 ANE regions**, MPSGraph delegate only
- `models/granite97m/macos/fp32-s128/aot-gpu/granite97m_fp32_s128_bound.h16g.aimodelc` (372 MB) — the `--preferred-compute gpu` control; same 0 ANE regions
- toolchain: `xcodebuild -downloadComponent MetalToolchain` (838.9 MB) → `coreai-build 3600.83.1` at `…/Metal.xctoolchain/usr/bin/coreai-build`
- traces are on disk only (`**/*.trace/` is gitignored); they are regenerable evidence, not sources
- `bench/coreai_neuralEngine_full.trace` (273 MB, kept on disk) — the full `Core AI` trace behind
  the Metal/ODIE numbers; regenerate with:
  ```bash
  xcrun xctrace record --template 'Core AI' --launch --output bench/coreai_neuralEngine_full.trace -- \
    tools/granite-runner/.build/out/Products/Release/granite-runner \
    models/granite97m/macos/fp32-s128/granite97m_fp32_s128_bound.aimodel \
    models/granite97m/macos/fp32-s128/tokenizer \
    models/granite97m/macos/fp32-s128/reference.json --compute neuralEngine --iters 3000
  ```

## Upstream value
Three findings, all confirmed on a **base M4**, macOS 27.0, coreai-kit 0.4.2:

**1. The card's *"Not tested: the Neural Engine"* is answered — negatively.**
`preferredComputeUnitKind: .neuralEngine` does **not** put this graph on the ANE. It runs on
the **GPU** (GPU rail 4421.6 mW; ANE rail 0.0 mW, below even the 6–10 mW idle floor the Core ML
control shows). The card lists "the Neural Engine" as untested and its Mac numbers as
GPU-preferred; we can now say the preference does not change that on base M4.

**2. You cannot audit Core AI placement with xctrace — at all.**
`ane-hw-intervals` reports **zero** intervals for Core AI graphs, **process-scoped *and*
system-wide**, while a Core ML control in the same session reports 1310. The Core AI-specific
table `ODIEProfile` (9,127 rows) carries `model-name`/`function-name`/`phase`/`category` but
**no compute-unit attribution**, and there is **no ANE-specific template** among the 25. Anyone
told that Xcode's Core AI instrument shows "which compute unit each op landed on" will not find
it. The only in-trace signal that works is `metal-gpu-intervals` (per-process); the only direct
ANE measurement is the power rails.

**3. The numeric gates pass on every placement** — `cpuOnly`, `cpu`, `gpu`, `neuralEngine`:
tokenizer 35/35 exact, cos ≥ 0.999999881, max \|err\| 2.98e-07, 0/35 failures. The kit's
documented "silently wrong numerics on some graphs" defect does **not** manifest here, which is
useful negative evidence for the same trap list.

**Open, testable next step:** reaching the ANE is an **authoring** problem, not a packaging or
runtime one. To get this model on the ANE it must be re-authored to the recipe the zoo documents
(`knowledge/compute-units-and-authoring.md`): **fp16**, **BC1S `(B, C, 1, S)` layout**, and
**1×1 Conv2d** projections instead of `nn.Linear`. Then re-run this exact pipeline and check
`find <bundle> -name '*ANE_region*' | wc -l` — anything above 0 means the ANE took it. Note the
card's own finding that whole-model fp16 fails its *layer* gate, so the re-authoring has to hold
numerics as well as placement.

---

## Measurements (generated)

> Generated from `results/measurements.json` by `bench/results_table.py`. **Do not hand-edit** — regenerate.
> Rows appear only when another row is genuinely comparable; `benchmark+split+scope+tiers+metric+unit`
> must agree. See `results/CONSISTENCY-PLAN.md` for why.

|---|---|---|---|---|---|---|---|---|---|---|
| granite-cpuonly-warm-median | Granite-Embedding-97M | cpuOnly | fp32 | 128 | warm median latency | 8.28 | ms | 8.28 | per embedding (warm median of 105 samples, S=128) | ours |
| granite-cpuonly-load | Granite-Embedding-97M | cpuOnly | fp32 | 128 | model load time | 594 | ms | 594 | per model load (one-off) | ours |
| granite-cpuonly-first-after-load | Granite-Embedding-97M | cpuOnly | fp32 | 128 | first inference after load | 19.58 | ms | 19.58 | per first inference after load | ours |
| granite-cpuonly-gate-cosine | Granite-Embedding-97M | cpuOnly | fp32 | 128 | cosine vs HF oracle | 1 | cosine | — | — | ours |
| granite-cpu-warm-median | Granite-Embedding-97M | cpu | fp32 | 128 | warm median latency | 8.28 | ms | 8.28 | per embedding (warm median of 105 samples, S=128) | ours |
| granite-cpu-load | Granite-Embedding-97M | cpu | fp32 | 128 | model load time | 392 | ms | 392 | per model load (one-off) | ours |
| granite-cpu-first-after-load | Granite-Embedding-97M | cpu | fp32 | 128 | first inference after load | 15.21 | ms | 15.21 | per first inference after load | ours |
| granite-cpu-gate-cosine | Granite-Embedding-97M | cpu | fp32 | 128 | cosine vs HF oracle | 1 | cosine | — | — | ours |
| granite-cpu-speedup-vs-cpuonly | Granite-Embedding-97M | cpu | fp32 | 128 | speedup vs cpuOnly | 1 | x vs cpuOnly (warm median) | — | — | ours |
| granite-gpu-warm-median | Granite-Embedding-97M | gpu | fp32 | 128 | warm median latency | 6.06 | ms | 6.06 | per embedding (warm median of 105 samples, S=128) | ours |
| granite-gpu-load | Granite-Embedding-97M | gpu | fp32 | 128 | model load time | 510 | ms | 510 | per model load (one-off) | ours |
| granite-gpu-first-after-load | Granite-Embedding-97M | gpu | fp32 | 128 | first inference after load | 741.2 | ms | 741.2 | per first inference after load | ours |
| granite-gpu-gate-cosine | Granite-Embedding-97M | gpu | fp32 | 128 | cosine vs HF oracle | 1 | cosine | — | — | ours |
| granite-gpu-speedup-vs-cpuonly | Granite-Embedding-97M | gpu | fp32 | 128 | speedup vs cpuOnly | 1.37 | x vs cpuOnly (warm median) | — | — | ours |
| granite-neuralengine-warm-median | Granite-Embedding-97M | neuralEngine | fp32 | 128 | warm median latency | 4.33 | ms | 4.33 | per embedding (warm median of 105 samples, S=128) | ours |
| granite-neuralengine-load | Granite-Embedding-97M | neuralEngine | fp32 | 128 | model load time | 474 | ms | 474 | per model load (one-off) | ours |
| granite-neuralengine-first-after-load | Granite-Embedding-97M | neuralEngine | fp32 | 128 | first inference after load | 21.24 | ms | 21.24 | per first inference after load | ours |
| granite-neuralengine-gate-cosine | Granite-Embedding-97M | neuralEngine | fp32 | 128 | cosine vs HF oracle | 1 | cosine | — | — | ours |
| granite-neuralengine-speedup-vs-cpuonly | Granite-Embedding-97M | neuralEngine | fp32 | 128 | speedup vs cpuOnly | 1.91 | x vs cpuOnly (warm median) | — | — | ours |
| xctrace-proc-granite-ane-intervals | Granite-Embedding-97M | neuralEngine | fp32 | 128 | ane-hw-intervals | 0 | intervals | — | — | ours |
| xctrace-proc-granite-cpuonly-intervals | Granite-Embedding-97M | cpuOnly | fp32 | 128 | ane-hw-intervals | 0 | intervals | — | — | ours |
| xctrace-proc-minilm-all-intervals | MiniLM Core ML | ALL | — | — | ane-hw-intervals | 269 | intervals | — | — | ours |
| xctrace-proc-minilm-all-busy | MiniLM Core ML | ALL | — | — | ane-hw-intervals busy time | 511.5 | ms | 511.5 | per trace capture (total ANE busy time) | ours |
| xctrace-syswide-minilm-all-intervals | MiniLM Core ML | ALL | — | — | ANE intervals | 1310 | intervals | — | — | ours |
| xctrace-syswide-minilm-all-busy | MiniLM Core ML | ALL | — | — | ANE busy time | 1012 | ms | 1012 | per trace capture (total ANE busy time) | ours |
| xctrace-syswide-minilm-all-mean | MiniLM Core ML | ALL | — | — | mean ANE interval | 0.77 | ms | 0.77 | per ANE interval (mean) | ours |
| xctrace-syswide-minilm-cpuandgpu-intervals | MiniLM Core ML | CPU_AND_GPU | — | — | ANE intervals | 0 | intervals | — | — | ours |
| xctrace-syswide-granite-cpuonly-intervals | Granite-Embedding-97M | cpuOnly | fp32 | 128 | ANE intervals | 0 | intervals | — | — | ours |
| xctrace-syswide-granite-ane-intervals | Granite-Embedding-97M | neuralEngine | fp32 | 128 | ANE intervals | 0 | intervals | — | — | ours |
| latsig-neuralengine-median | Granite-Embedding-97M | neuralEngine | fp32 | 128 | median latency | 4.331 | ms | 4.331 | per embedding (1200 warm inferences per round) | ours |
| latsig-neuralengine-spread | Granite-Embedding-97M | neuralEngine | fp32 | 128 | spread over 5 runs | 0.015 | ms | — | — | ours |
| latsig-gpu-median | Granite-Embedding-97M | gpu | fp32 | 128 | median latency | 4.982 | ms | 4.982 | per embedding (1200 warm inferences per round) | ours |
| latsig-gpu-spread | Granite-Embedding-97M | gpu | fp32 | 128 | spread over 5 runs | 0.461 | ms | — | — | ours |
| latsig-cpuonly-median | Granite-Embedding-97M | cpuOnly | fp32 | 128 | median latency | 8.164 | ms | 8.164 | per embedding (1200 warm inferences per round) | ours |
| latsig-cpuonly-spread | Granite-Embedding-97M | cpuOnly | fp32 | 128 | spread over 5 runs | 0.109 | ms | — | — | ours |
| power-neuralengine-median | Granite-Embedding-97M | neuralEngine | fp32 | 128 | median latency | 4.3 | ms | 4.3 | per embedding (3000 inferences per arm) | ours |
| power-neuralengine-ane-mw | Granite-Embedding-97M | neuralEngine | fp32 | 128 | ANE power (median) | 0 | mW | — | — | ours |
| power-neuralengine-gpu-mw | Granite-Embedding-97M | neuralEngine | fp32 | 128 | GPU power (median) | 4422 | mW | — | — | ours |
| power-neuralengine-cpu-mw | Granite-Embedding-97M | neuralEngine | fp32 | 128 | CPU power (median) | 3229 | mW | — | — | ours |
| power-gpu-median | Granite-Embedding-97M | gpu | fp32 | 128 | median latency | 5.55 | ms | 5.55 | per embedding (3000 inferences per arm) | ours |
| power-gpu-ane-mw | Granite-Embedding-97M | gpu | fp32 | 128 | ANE power (median) | 0 | mW | — | — | ours |
| power-gpu-gpu-mw | Granite-Embedding-97M | gpu | fp32 | 128 | GPU power (median) | 3408 | mW | — | — | ours |
| power-gpu-cpu-mw | Granite-Embedding-97M | gpu | fp32 | 128 | CPU power (median) | 2202 | mW | — | — | ours |
| power-cpuonly-median | Granite-Embedding-97M | cpuOnly | fp32 | 128 | median latency | 8.04 | ms | 8.04 | per embedding (3000 inferences per arm) | ours |
| power-cpuonly-ane-mw | Granite-Embedding-97M | cpuOnly | fp32 | 128 | ANE power (median) | 0 | mW | — | — | ours |
| power-cpuonly-gpu-mw | Granite-Embedding-97M | cpuOnly | fp32 | 128 | GPU power (median) | 0.3 | mW | — | — | ours |
| power-cpuonly-cpu-mw | Granite-Embedding-97M | cpuOnly | fp32 | 128 | CPU power (median) | 6085 | mW | — | — | ours |
| trace-metal-gpu-intervals | Granite-Embedding-97M | neuralEngine | fp32 | 128 | metal-gpu-intervals | 54846 | rows/intervals | — | — | ours |
| trace-metal-command-buffer-completed | Granite-Embedding-97M | neuralEngine | fp32 | 128 | metal-command-buffer-completed | 61920 | rows/intervals | — | — | ours |
| trace-metal-gpu-state-intervals | Granite-Embedding-97M | neuralEngine | fp32 | 128 | metal-gpu-state-intervals | 113172 | rows/intervals | — | — | ours |
| trace-ane-hw-intervals | Granite-Embedding-97M | neuralEngine | fp32 | 128 | ane-hw-intervals | 0 | rows/intervals | — | — | ours |
| enginemon-amc-stats-ane-dcs-rd-ne | Granite-Embedding-97M | neuralEngine | fp32 | 128 | AMC Stats -> ANE DCS RD | 0 | bytes | — | — | ours |
| enginemon-amc-stats-ane-dcs-rd-gpu | Granite-Embedding-97M | gpu | fp32 | 128 | AMC Stats -> ANE DCS RD | 0 | bytes | — | — | ours |
| enginemon-amc-stats-ane-dcs-rd-minilm-all | MiniLM Core ML | ALL | — | — | AMC Stats -> ANE DCS RD | 128 | bytes (Core ML ALL reported as range 128-171 GB) | — | — | ours |
| enginemon-amc-stats-ane-nrt-af-rd-ne | Granite-Embedding-97M | neuralEngine | fp32 | 128 | AMC Stats -> ANE NRT AF RD | 0 | bytes | — | — | ours |
| enginemon-amc-stats-ane-nrt-af-rd-gpu | Granite-Embedding-97M | gpu | fp32 | 128 | AMC Stats -> ANE NRT AF RD | 0 | bytes | — | — | ours |
| enginemon-amc-stats-ane-nrt-af-rd-minilm-all | MiniLM Core ML | ALL | — | — | AMC Stats -> ANE NRT AF RD | 184 | GB | — | — | ours |
| enginemon-pmp-ane0-rd-ne | Granite-Embedding-97M | neuralEngine | fp32 | 128 | PMP -> ANE0 RD | 0 | events | — | — | ours |
| enginemon-pmp-ane0-rd-gpu | Granite-Embedding-97M | gpu | fp32 | 128 | PMP -> ANE0 RD | 0 | events | — | — | ours |
| enginemon-pmp-ane0-rd-minilm-all | MiniLM Core ML | ALL | — | — | PMP -> ANE0 RD | 29252 | events | — | — | ours |
| enginemon-ane-0-interrupts-ne | Granite-Embedding-97M | neuralEngine | fp32 | 128 | ane 0 interrupts | 0 | interrupts | — | — | ours |
| enginemon-ane-0-interrupts-gpu | Granite-Embedding-97M | gpu | fp32 | 128 | ane 0 interrupts | 0 | interrupts | — | — | ours |
| enginemon-ane-0-interrupts-minilm-all | MiniLM Core ML | ALL | — | — | ane 0 interrupts | 24538 | interrupts (reported range 24538-37368) | — | — | ours |
| enginemon-energy-model-gpu-energy-ne | Granite-Embedding-97M | neuralEngine | fp32 | 128 | Energy Model -> GPU Energy | 6173 | mW | — | — | ours |
| enginemon-energy-model-gpu-energy-gpu | Granite-Embedding-97M | gpu | fp32 | 128 | Energy Model -> GPU Energy | 3101 | mW | — | — | ours |
| enginemon-energy-model-gpu-energy-minilm-all | MiniLM Core ML | ALL | — | — | Energy Model -> GPU Energy | 14 | mW (approx) | — | — | ours |
| aot-jit-ane-traffic | Granite-Embedding-97M | neuralEngine | fp32 | 128 | ANE memory traffic | 0 | B | — | — | ours |
| aot-jit-ane-interrupts | Granite-Embedding-97M | neuralEngine | fp32 | 128 | ANE interrupts | 0 | interrupts | — | — | ours |
| aot-jit-gpu-power | Granite-Embedding-97M | neuralEngine | fp32 | 128 | GPU power | 6173 | mW | — | — | ours |
| aot-aimodelc-ane-traffic | Granite-Embedding-97M | neuralEngine | fp32 | 128 | ANE memory traffic | 0 | B | — | — | ours |
| aot-aimodelc-ane-interrupts | Granite-Embedding-97M | neuralEngine | fp32 | 128 | ANE interrupts | 0 | interrupts | — | — | ours |
| aot-aimodelc-gpu-power | Granite-Embedding-97M | neuralEngine | fp32 | 128 | GPU power | 1.071e+04 | mW | — | — | ours |
| aot-aimodelc-gate-cosine | Granite-Embedding-97M | neuralEngine | fp32 | 128 | cosine vs HF oracle | 1 | cosine | — | — | ours |
| aot-aimodelc-latency | Granite-Embedding-97M | neuralEngine | fp32 | 128 | latency | 4.312 | ms | 4.312 | per embedding (AOT .aimodelc gate run) | ours |
| aot-aimodelc-tokenizer-parity | Granite-Embedding-97M | neuralEngine | fp32 | 128 | tokenizer parity | 35 | of 35 exact | — | — | ours |
| coreai-build-ne-macos-ane-regions | Granite-Embedding-97M | neuralEngine | — | — | ANE regions | 0 | regions | — | — | ours |
| coreai-build-gpu-macos-ane-regions | Granite-Embedding-97M | gpu | — | — | ANE regions | 0 | regions | — | — | ours |
| coreai-build-ne-ios-ane-regions | Granite-Embedding-97M | neuralEngine | — | — | ANE regions | 0 | regions | — | — | ours |
| odie-category-inference | granite97m_fp32_s128_bound | neuralEngine | — | — | ODIEProfile rows (category=Inference) | 6080 | rows | — | — | ours |
| odie-category-setup | granite97m_fp32_s128_bound | neuralEngine | — | — | ODIEProfile rows (category=Setup) | 3043 | rows | — | — | ours |
| odie-category-load | granite97m_fp32_s128_bound | neuralEngine | — | — | ODIEProfile rows (category=Load) | 4 | rows | — | — | ours |
| odie-phase-inference | granite97m_fp32_s128_bound | neuralEngine | — | — | ODIEProfile rows (phase=Inference) | 9123 | rows | — | — | ours |
| odie-phase-load | granite97m_fp32_s128_bound | neuralEngine | — | — | ODIEProfile rows (phase=Load) | 4 | rows | — | — | ours |
| odie-color-blue | granite97m_fp32_s128_bound | neuralEngine | — | — | ODIEProfile rows (color=Blue) | 6080 | rows | — | — | ours |
| odie-color-purple | granite97m_fp32_s128_bound | neuralEngine | — | — | ODIEProfile rows (color=Purple) | 3043 | rows | — | — | ours |
| odie-color-teal | granite97m_fp32_s128_bound | neuralEngine | — | — | ODIEProfile rows (color=Teal) | 4 | rows | — | — | ours |
| odie-function-name-main | granite97m_fp32_s128_bound | neuralEngine | — | — | ODIEProfile rows (function-name=main) | 9125 | rows | — | — | ours |
| odie-profile-total-rows | granite97m_fp32_s128_bound | neuralEngine | — | — | ODIEProfile total rows | 9127 | rows | — | — | ours |
