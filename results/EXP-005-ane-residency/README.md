# EXP-005 — Getting Core AI onto the Neural Engine (base M4)

**Question.** EXP-004 established that the published Granite-Embedding-97M bundle never reaches
the ANE: `.neuralEngine` is a *preference*, and this graph compiles to **0 ANE regions** — the
zoo's own definition of *"silent GPU fallback"*. Can the graph be made to run on the ANE, and
what does it cost?

**Answer.** Yes. Three small, surgical changes — one dtype and two fp32 ops — turn a GPU-only
graph into an ANE-resident one that is **slightly faster, loads 2× faster, and uses ~125× less
GPU power** than the published fp32 variant.

**Run:** 2026-09-20 · macOS 27.0 (26A428) · Xcode 27.0 (27A266a) · coreai-build 3600.83.1 ·
arch **h16g** (M4) · S=128 · fp16 · measured with `tools/enginemon` (unprivileged)

---

## Step 1 — dtype is necessary, and it is the first blocker

Apple's authoring rules are explicit:

> **Supported dtypes**: fp16, int8, int16. **fp32 falls back to GPU/CPU.**

Control probe (`bench/probe_ane_regions.py`) — one tiny ANE-shaped graph (1×1 Conv2d, BC1S,
channel LayerNorm), **dtype the only variable**:

| arm | ANE regions (corrected, F-27) |
| --- | ---: |
| fp16 | **66** |
| fp32 | **0** |

So macOS Core AI *can* target the ANE, and fp32 cannot. Applied to the real graph — a straight
`--dtype fp16` re-export, nothing else changed:

| variant | ANE regions |
| --- | ---: |
| fp32 (published) | **0** |
| **fp16** | **14** |

**fp16 alone unlocks the ANE.** Note the zoo rejected fp16 for *numerics* ("fp16 fails the
authoring layer gate on this checkpoint; fp32 ships") — a correct call for shipping, but fp16
had never been checked for *placement*, and it is the single change that matters for it.

## Step 2 — the fp32 ops decide how *well* it runs

`bench/granite_ane_variants.py` patches the graph's f32-isms one at a time, in memory (the
zoo's file is untouched). Apple: *"Any Python float literal or fp32 op creates an f32 buffer
that Neural Engine cannot execute — it falls back to GPU/CPU."*

| variant | change |
| --- | --- |
| v0 | as-is: `F.softmax(..., dtype=torch.float32)`, `head_dim ** -0.5` float literal, `pooled.float()` |
| v1 | softmax in the graph dtype |
| v2 | + scale as an f16 buffer |
| v3 | + pooling without the `.float()` cast |

| variant | ANE regions | ANE moved | ANE interrupts | **GPU mW** | load | warm median | min cosine | max \|err\| |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fp32 (published, GPU) | 0 | 0.0 GB | 0 | **10,390** | 122 ms | 4.33 ms | 0.999999881 | 2.98e-07 |
| fp16 v0 as-is | 13 | 91.7 GB | 122,832 | 333 | 87 ms | 13.14 ms | 0.999957561 | 1.46e-03 |
| fp16 v1 +fp16 softmax | 1 | 87.7 GB | 15,050 | 125 | 271 ms | 5.18 ms | 0.999958634 | 1.40e-03 |
| fp16 v2 +f16 scale | 1 | 87.7 GB | 14,848 | 127 | 55 ms | 5.24 ms | 0.999958634 | 1.40e-03 |
| **fp16 v3 +fp16 pooling** | 1 | 87.7 GB | 13,472 | **83** | **55 ms** | **4.00 ms** | 0.999995216 | 1.58e-03 |

(Two passes; pass 1's load column was cold-cache contaminated — 2813 ms vs 55 ms for the same
variant — and is excluded above. Warm medians and power were stable across passes.)

### What the numbers say

1. **v0 → v1 is the big jump.** Removing the fp32 softmax cut warm median **13.14 → 5.18 ms**
   and GPU power **333 → 125 mW**. The fp32 buffer was forcing a GPU round-trip inside every
   attention layer.
2. **v3 beats the published fp32 path outright**: **4.00 vs 4.33 ms**, load **55 vs 122 ms**,
   GPU **83 vs 10,390 mW** (125× less). The ANE is not a downgrade here — it is faster.
3. **Fewer regions is better, not worse.** v0 had 13 regions and 122,832 interrupts; v3 has 1
   and 13,472 — while ANE bytes moved stayed ~88 GB. Fewer, larger regions means fewer
   ANE↔GPU segment boundaries. (The zoo saw the same: 49 → 25 regions halved their load time.)
   **Region count is a shape metric, not a quality metric** — recorded as F-26.
4. **The dtype change alone is not enough.** v0 is fp16 *and* on the ANE, but it is **3× slower
   than the GPU path** (13.14 vs 4.33 ms). "It runs on the ANE" and "it runs well on the ANE"
   are different claims, and only the second one is worth shipping.

## Step 3 — is it *usable*? The zoo's own gate says yes

Cosine alone does not answer this. For an embedder the question is whether **retrieval**
survives. `bench/gate_precision_report.py` runs the zoo's complete gate (`_gate_metrics.py`,
shared by every stage) on embeddings dumped from the **actual runtime** via
`granite-runner --dump-embeddings` — not from the torch graph.

| variant | status | min cosine | max \|err\| | norm err | top-1 all | clear pair flips | worst score err |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| fp32 (published) | PASS | 1.000000000 | 2.98e-07 | 1.89e-07 | True | **0** | 1.64e-07 |
| **fp16 v3** | **PASS** | 0.999958868 | 1.58e-03 | 5.92e-04 | **True** | **0** | 2.20e-03 |
| *(threshold)* | | ≥ 0.999 | ≤ 0.02 | ≤ 0.002 | exact | **0** | ≤ 0.01 |

Every threshold passes with margin (cosine 24× over the floor, err 12× under the cap, score
error 4.5× under). **Retrieval is intact: 4/4 queries keep their exact top-1, and no document
pair the fp32 oracle separates by ≥ 0.001 inverts.**

**Context for the precision concern.** The zoo **shipped** a w8 variant at cos **0.999410**,
max \|err\| **5.67e-03** — *less precise than our fp16* (0.9999589 / 1.58e-03) — accepted on
"4/4 retrieval top-1s, 0 clear-pair flips". Our fp16 is ~4× more precise than a variant that
already ships.

**The one gate fp16 fails is the layer gate** (per-hidden-state max \|err\| ≤ 1e-4). That gate
exists to catch **graph bugs**, not to certify output precision: its documented purpose is that
a sliding-window of 63 instead of 64 "passes the embedding gate (cos 0.99995) and fails only
the layer gate". A uniform precision reduction is a different animal from a structural error,
which is why the embedding+retrieval gate is the right instrument for this question.

**Honest limit:** the fixture set is a **parity instrument (35 texts, 4 queries, 12 documents),
not a benchmark** — the zoo says so itself. Retrieval preservation is demonstrated *on this
instrument*; a shipping claim would need a real retrieval benchmark.

### The precision/speed dial

| variant | pooling | warm median | GPU mW | max \|err\| |
| --- | --- | ---: | ---: | ---: |
| v2 | fp32 (`pooled.float()`) | 5.24 ms | 127 | **1.40e-03** |
| v3 | fp16 | **4.00 ms** | **83** | 1.58e-03 |

Both pass the gate. v2 is the conservative choice (13% more precise, 31% slower); v3 is the
fast one. If more precision were needed it is a *tuning* knob, not a re-authoring project —
and for the highest-value case (candidate generation) a two-stage scheme (fp16 retrieve →
fp32 rescore the top-k) is the standard answer.

## Step 4 — the dtype ceiling: why fp8 can't help, and what can

**Is there fp8?** Yes in the *catalog*, no in the *silicon*:

| | evidence |
| --- | --- |
| fp8 types exist in Core AI | `coreai.runtime._ndarray` lists `float8e4m3fn`, `float8e5m2`, `float8e8m0fn`, `float4e2m1fn`, `int2`, `int4`; `CoreAI.tbd` exports `E4M3`, `E5M2`, `Float8` |
| fp8 has no ANE datapath here | zoo `knowledge/ane-silicon-reference.md`: *"fp8 (e4m3) exists in the element-type catalog but the datapath is **H18 (A18)-only**"* |
| the ANE's documented menu | Apple's rules: **fp16, int8, int16** — fp8 is not among them |
| fp8's real home | **TensorOps** (`matmul2d`) on **M5/A19 GPU shader cores**, OS 27, aimed at compute-bound prefill — a GPU lever, not an ANE one, and not this machine |

⚠️ **Direct test attempted and blocked:** exporting an fp8 arm failed at the *torch* level
(`normal_kernel_cpu not implemented for 'Float8_e4m3fn'`) — torch cannot even materialise fp8
tensors on CPU. So the fp8 conclusion rests on documentation, not on our own measurement.
Flagged rather than glossed.

**More important: dtype is now exhausted as a lever.** `coreai-build inspect` on fp32 vs v3:

| | fp32 | fp16 v3 |
| --- | --- | --- |
| storage | **Float32 = 97,457,544** | **Float16 = 97,457,542**, Float32 = **2** |
| compute | Bool, **Float32**, Int32, UInt32, UInt64 | Bool, **Float16**, Float32, Int32, UInt32, UInt64 |
| op distribution | 169 reshape, 141 broadcast_in_dims, 114 mul, 109 slice, 84 transpose, 72 batch_matmul, 72 concat, 36 split | **identical** |

v3 is **99.999998% fp16** (two fp32 elements left) — and still emits 1 ANE region plus
MPSGraph delegates. So the remaining GPU residency is **structural, not dtype-driven**: the op
mix is unchanged and it is standard-layout data movement (`reshape` / `broadcast_in_dims` /
`transpose` / `batch_matmul`), exactly what Apple's rules say the ANE handles poorly
(*"Reshapes and transposes that touch the width (innermost) dimension are especially
expensive"*).

**So the honest answer to "can we throw more ops at the ANE?" is: not with another dtype.**
Two levers were identified; one is now measured (Step 5) and it is a **negative result**:

1. ~~int8 / palettization~~ — **tested in Step 5: 4.8× slower.** It is a *storage* lever for this
   graph, not a compute one. The ANE's double-int8 compute rate needs **W8A8** (int8
   activations), not the W8A16 weight-only palettization the zoo's preset provides.
2. **Structural re-authoring** (BC1S layout, 1×1 Conv2d, per-head attention) — the only
   remaining lever that addresses the segmentation, since that is what the op mix reflects.
   Note it keeps fp16, so it is a **performance** change, not a precision fix.

## Step 5 — int8 weight palettization: a size lever, not a compute lever (negative result)

The zoo ships a **w8** variant of this model — but with **fp32 compute** ("all compute stay
fp32"), which cannot form ANE regions. Its notes also mention a *"w8 + fp16-table build
(167 MB) passed the same CPU gates but was not device-qualified"*. Nobody had compiled that
combination for the ANE, so `bench/export_granite_w8_fp16.py` does: the zoo's exact
`KMeansPalettizerConfig.presets.w8()` on the same 48 linears, seed 0 — with the model loaded in
**fp16** instead of fp32. (The zoo's file is untouched; its dtype line is the only difference.)

| arm | ANE moved | ANE intr | GPU mW | load | **warm ms** | cos | max \|err\| | size |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fp32 (published, GPU) | 0.0 GB | 0 | 8025 | 797 ms | 4.31 ms | 0.999999881 | 2.98e-07 | 390 MB |
| **fp16 v3** | 87.7 GB | 13,730 | **62.7** | **257 ms** | **4.05 ms** | 0.999958634 | 1.58e-03 | 195 MB |
| **w8 + fp16** | 59.9 GB | 83,050 | 241.6 | 2131 ms | **19.48 ms** | 0.999383390 | 6.09e-03 | **167 MB** |

**int8 weight palettization made it 4.8× SLOWER** (19.48 vs 4.05 ms), with a 39× worse load and
a 6× higher ANE interrupt count (more segmentation churn). It did shrink the bundle to 167 MB
(2.3× smaller than fp32).

**Why — and Apple's rules say it outright:**

> *"Compression reduces model size but does not always improve performance — the benefit depends
> on whether the layer is bottlenecked by **weight loading** rather than computation. … Layers
> that are already **compute-bound** will not see performance gains from compression alone."*

This graph is not weight-load-bound, so halving the weight stream buys nothing while the 48
`lut_to_dense` reconstructions (LUT + indices → dense weight, before each matmul) add real work.
The zoo saw the same thing on the phone: their w8 was *"not faster on the phone (6.64 / 23.07 ms
vs 5.54 / 20.99)"*.

**The distinction that matters:** this is **W8A16** — int8 *weights*, fp16 *activations*. The
ANE's documented **double-int8 compute mode (~1.4–2× the fp16 rate)** applies to int8
*arithmetic*, i.e. **W8A8**, which would require quantizing **activations** — a different and
riskier change that the zoo's preset deliberately excludes (`op_input_spec`/`op_output_spec`
must be None: *"unexpected activation compression"*).

**Conclusion: for this graph the compute lever is fp16, and weight compression is a storage
lever.** int8 does not throw more work onto the ANE — it adds work.

## Step 6 — the segmentation cost, measured (and two corrections to my own numbers)

### Correction 1 — my ANE region counts were wrong (F-27)

I counted with `find <bundle> -name '*ANE_region*'`, which matches a **directory** and the file
**inside** it, double-counting every region. The zoo's documented glob is
`find <bundle> -name '*ANE_region_*.mlir.bc'`. Corrected counts:

| variant | correct | I reported |
| --- | ---: | ---: |
| fp32 published | 0 | 0 |
| fp16 v0 | **13** | 14 |
| fp16 v1 / v2 / v3 | **1** | 2 |
| w8 + fp16 | **13** | 14 |

The ordering and every conclusion survive — but the numbers were inflated, and a count that is
off by one on a metric used as a *gate* is not acceptable. Logged as **F-27**.

### What the segmentation actually is

The bundle is **one MPSGraph package that embeds the ANE regions**:

| component | bytes |
| --- | ---: |
| `resources.bin` (weights) | 194,917,488 |
| **ANE region `.mlir.bc`** | **403,651** |
| MPSGraph `original_model_0.mpsgraph` | 121,802 |
| MPSGraph `specialized_model_1.mpsgraph` | 99,715 |

The manifest carries an `ANERegionsHash` per architecture. With **1 region**, the shape is
*GPU prologue → ANE (the 12-layer body) → GPU epilogue* — the near-ideal arrangement.

### The cost of extra boundaries

Same graph, same precision, only the region count differs:

| build | regions | converged median (4000 iters) |
| --- | ---: | ---: |
| fp16 v0 (fp32 softmax inside the layer loop) | 13 | **13.19 ms** |
| fp16 v3 (fp32 ops removed) | 1 | **4.60 ms** |

**~12 extra boundaries cost ~8.6 ms** — the dominant cost in the whole exercise, and it was
caused by GPU *execution* of the fp32 softmax inside every layer, not by data transfer (a
(1,128,384) fp16 boundary tensor is ~98 KB, i.e. ~1 µs at ~100 GB/s; 24 transfers ≈ 24 µs, not
8 ms). The cost is per-dispatch latency on a GPU that must be woken inside the layer loop.

### The ANE at 1 region vs the GPU at the same precision

| path | median | min | GPU power |
| --- | ---: | ---: | ---: |
| fp16 v3 on **ANE** (1 region) | 4.60 ms *(2.17 ms in another run)* | **1.85 ms** | **75 mW** |
| fp16 v3 on **GPU** (same bundle, `--compute gpu`) | 5.52 ms | 4.58 ms | 4124 mW |
| fp32 published on **GPU** | 4.31 ms | 4.17 ms | 8025 mW |

When the ANE runs, the GPU draws **75 mW against 4124 mW** for the pure-GPU path — **~1.8%** —
so the ANE holds essentially all of the work and the residual GPU part is prologue/epilogue.

### Correction 2 — the ANE latency is bimodal, and my earlier numbers were one sample of it

Repeating the identical run: medians of **2.14, 2.15, 2.15, 2.17, 2.40, 3.38, 3.77, 4.26, 4.60,
4.90 ms** — while `min` stayed at **1.78–1.90 ms** in every single run. A 4000-iteration run is
*not* enough to converge it (one gave 2.17, another 4.60). The GPU path over the same bundle is
stable (4.55–4.70 ms, min 4.10–4.41). So:

- the ANE's **fast state is ~1.8 ms** and is always reachable;
- there is a **slow tail at ~5.6 ms** (p95 is 5.5–5.8 in every ANE run);
- which state dominates is decided **per run**, not by run length.

**Consequence for every number in this record:** single-run latencies for ANE builds carry up to
a **2.1× spread**. `min` is the stable statistic; medians must be reported with the range. This
does not affect the region-count conclusion (13 vs 1 regions differ by 3× with *overlapping*
state mixes), but it does mean the earlier "v3 = 4.05 ms" was one sample of a 2.17–4.90 ms range.

**Open item (honest blind spot):** the cause of the slow tail is unidentified. Candidates:
ANE power-state transitions between dispatches, a periodic background ANE consumer, or buffer
recycling in the MPSGraph host. `tools/enginemon` shows **0 B / 0 interrupts** on an idle system,
so it is not a persistent background user. Resolving it needs a trace correlating slow samples
with `ane-hw-intervals` / `metal-gpu-intervals` — not done.

### Verdict on the refactoring

**Not justified by segmentation.** v3 already sits at **1 ANE region** — the minimum — with the
GPU doing ~1.8% of the work. The BC1S / 1×1 Conv2d / per-head rewrite targets exactly the
boundaries that are already gone. Its remaining plausible benefit (moving the prologue/epilogue
onto the ANE) is bounded by ~2 boundaries that we cannot show are expensive, and the rewrite
would keep fp16, so it is not a precision fix either.

The honest position: **the measured evidence does not support the refactoring.** If it is done
anyway, it should be justified by something else — e.g. portability to iOS/h18p, where the zoo's
ANE work actually ships.

## Step 7 — the ANE has two throughput states (burst vs sustained)

This started as an unexplained "bimodality" in the ANE latency and is now characterised.

### What was measured

**1. A per-inference weight stream that exceeds the on-chip scratchpad.** The 48 transformer
linears are **56.6 MB** in fp16; each inference moves **57–63 MB** of ANE traffic (measured). The
M4's ANE scratchpad is **~32 MB**, compiler-managed rather than a hardware cache, and the
literature reports degradation beginning above a **~24 MB** working set (maderix; Orion's SRAM
annotation). So the weight stream is ~1.8× the scratchpad and cannot be resident.

**2. Two throughput states, differing by ~2.1× in both bandwidth and latency:**

| state | latency | effective ANE bandwidth |
| --- | ---: | ---: |
| fast | **1.85–2.25 ms** | **~31 GB/s** |
| slow | **~4.75 ms** | **~14.5 GB/s** |

Both figures move together by the same factor, which is the signature of a **clock/throughput**
change rather than a data-location change (a cache effect would alter bytes moved, not the rate).

**3. Within a long run the transition is one-way.** A 20,000-inference run: samples **0–830 fast**,
samples **831–20,000 slow** — 19,169 consecutive, no flipping back.

**4. It is a burst-vs-sustained effect, not a per-run lottery.** Ten back-to-back bursts of
**120 inferences each** were **fast (2.13–2.25 ms in 8 of 10)** — while a 1200-inference run in the
same period showed a fast phase of only 258–385 samples. So short bursts stay fast; sustained runs
degrade. The same burst pattern on the **GPU** gives 1.9–2.6 ms, so the effect is not ANE-exclusive.

**5. It does not recover with idle time.** 45 s: fast phase 6/2000. **4 minutes: 21/1500.**
A page-cache explanation was tested directly — `cat`-ing the 186 MB `resources.bin` into the OS
cache before a run made it *worse* (385 → 258 fast samples), and correctly so: the ANE reads
weights from unified memory either way, so file residency is irrelevant.

**6. No thermal warning.** `pmset -g therm` reports none, and the user independently confirmed the
machine is far too efficient to throttle in 2 s.

### What it means

The fast state is a **burst** condition (short windows, ~31 GB/s); sustained work settles to
~14.5 GB/s and stays there for minutes. Thermals are excluded, page cache is excluded, and the
GPU shows the same shape. The remaining candidates are **ANE power/clock management with a long
recovery constant**, or **arbitration with another ANE client** (macOS runs `mediaanalysisd` and
`photoanalysisd`, both ML daemons, though an idle 20 s monitor showed 0 B / 0 interrupts).

**Practical consequence — and it changes the recommendation:**

| workload shape | better engine |
| --- | --- |
| short bursts (< ~0.5 s), cold start, latency-sensitive | **ANE** — 1.85–2.2 ms, load 257 ms |
| sustained throughput | **roughly at parity** — ANE ~4.75 ms vs GPU 4.6–5.5 ms |
| **any** shape, on power | **ANE wins outright** — 75 mW vs 4124 mW |

So the ANE's durable advantage is **energy and load time**, not sustained speed. That is a
sharper conclusion than "the ANE is 2× faster", and it is the one the measurements support.

### A mechanism for the Step-5 negative result

The guide's numerics chapter documents a **streaming gate** on compressed weights:

> *"A format that **streams** moves fewer bytes across the DRAM boundary; a format that **folds**
> yields the storage saving but not the bandwidth… The int8 fold is a **stored-size saving only**
> … reconstructed to fp16 in DRAM before the data-movement step, so a weight-streaming-bound
> matmul moves the same bytes as fp16 and runs at the fp16 latency."*

int8-affine weights **fold** on the M1 generation (int4-palette and sparse **stream**). If the w8
palettization folds, it saves disk but not bandwidth — which is exactly what we measured: w8+fp16
was **4.8× slower** despite a 2.3× smaller bundle. A streaming format (int4 palette) is the
theoretically right lever, but the zoo reports **4-bit does not compile for the ANE**.

### The full palettization sweep (int4 and int6 attempted)

`bench/export_granite_w8_fp16.py --bits {4,6,8}` — the zoo reports *"4-bit g8 does not compile
for the ANE"*; we tested it anyway, and with **group 16** rather than their g8, so the group size
is not the explanation.

| variant | ANE regions | gate | min cosine | clear pair flips | size |
| --- | ---: | --- | ---: | ---: | ---: |
| **fp16 (v3)** | **1** | **PASS** | 0.9999586 | **0** | 195 MB |
| w8 + fp16 | 13 | PASS | 0.9993834 | 0 | 167 MB |
| **w6 + fp16** | **14** | **FAIL** | 0.9983865 | **1** | 160 MB |
| **w4 + fp16** | **0** | **FAIL** | 0.9621623 | **16** | 153 MB |

**int4 fails twice over**: it does not form a single ANE region (so it runs on the GPU), *and* it
destroys retrieval — 16 pair inversions, cosine 0.962. **int6 compiles (14 regions) but fails the
gate** (cosine below 0.999, one pair flip). **int8 compiles and passes but is slower** (folds, so
no bandwidth gain — Step 5).

**The compression axis is therefore exhausted for this graph:** every option either fails to
compile for the ANE, fails quality, or is slower. Independently reproduces the zoo's 4-bit
finding, and shows 6-bit is also not viable *for this model* (it shipped for a 2B LLM).

### Power measurement: what our own tool can and cannot see

Asked to check power during the transition, the honest answer is that **enginemon cannot see ANE
power**. Running it unfiltered during an ANE workload, the only *power* channel that moves is
`GPU Energy`; the `Energy Model -> ANE` channel is frozen (F-24). What enginemon does see is ANE
**traffic** (`ANE DCS RD/WR`, `AFI AF RD/WR`, `ECPU`/`PCPU` traffic) and **interrupts**.

So the burst/sustained discriminator needs `powermetrics` (root):
`bench/power_phase_probe.py` samples `ane_power,gpu_power,cpu_power` at 200 ms while a long ANE
run dumps its latency series, splits the power samples at the measured transition, and reports
both windows. The reading is unambiguous:

- **ANE power falls with the slowdown** -> clock/power state (DVFS-like)
- **ANE power is flat** -> a bandwidth ceiling, not a clock drop

### CORRECTION — the ANE power rail works; my "blind instruments" claim was wrong

Running the power A/B on the **fp16** bundle across all three compute units settles it:

| `--compute` | gate | median | **ANE mW** | GPU mW | CPU mW |
| --- | --- | ---: | ---: | ---: | ---: |
| `neuralEngine` | PASS | 2.14 ms | **1914.4** | 361.4 | 986.9 |
| `gpu` | PASS | 1.94 ms | **1792.4** | 445.8 | 1152.3 |
| `cpuOnly` | — | — | **8.0** | 2.0 | 714.2 |

**The ANE rail reports Core AI's ANE power perfectly: ~1.9 W under load, 8 mW idle.** So:

1. **My claim that "both standard ANE instruments are blind to Core AI" was WRONG.** It was
   generalised from EXP-004, where the arms read 0.0 mW — but those arms were the **fp32** bundle,
   which compiles to **0 ANE regions** and genuinely runs on the GPU. **The zeros were correct.**
   The `xctrace ane-hw-intervals` blindness is real and separately verified (system-wide capture,
   working control); the power rail is not blind.
2. **The ANE conclusion is now confirmed by a third independent instrument.** Power: ~1.9 W under
   load vs 8 mW idle, a ~240× ratio. (Alongside the 1 ANE region in the artifact and the IOReport
   traffic/interrupt counters.)
3. **`--compute gpu` on the AOT bundle still draws 1792 mW of ANE power** — placement is baked at
   compile time, now confirmed by power as well as by traffic (91.2 GB earlier).
4. The elevated CPU power I flagged as suspicious (6.6 W) was an artefact of the buggy parser
   below; the real figure is ~1 W.

### An instrument conflict that turned out to be my bug (F-29)

First attempt (`--iters 4000`) **never entered the slow state** — fast phase 3952/4000 (99%) — so
the split left **n=1** in the "sustained" window and the probe printed a verdict anyway. That is a
bug in the probe (fixed: it now refuses a verdict below 3 samples per window) and it is logged as
**F-28**. The state varies across a session, so a transition must be *caught*, not assumed.

The phase probe's first run reported ANE power of **0–14 mW** and CPU up to **6.6 W**, which
looked like a genuine conflict with the IOReport counters (173 GB of ANE traffic). It was not a
conflict — it was a **bug in the probe's parser**: it split the powermetrics output into sample
blocks with its own regexes and **silently dropped most samples** (14 parsed where ~51 were
expected), leaving fields that did not match `power_coreai.py`'s readings for the same workload.

Fixed: the probe now uses the same validated `power_ab.parse_power` as `power_coreai.py`, writes
the **raw powermetrics log** so any disagreement is checkable, and refuses a verdict when either
window has fewer than 3 samples. Logged as **F-29** — the same family as F-28: a tool that
answers when it should stay silent.

### Closing note — ANE power is not a usable instrument here

A second phase-resolved run (400 samples, 200 ms) gave the **opposite** answer to
`power_coreai.py` for the same workload:

| run | tool | ANE power |
| --- | --- | ---: |
| `power_coreai.py` | validated parser, 500 ms, averaged | **1914 mW** |
| `power_phase_probe.py` | 400 samples, 200 ms, full series | **~0 mW for ~11 of 13 s** |

The series lights the ANE only at samples 11–15 (359 → 3022 mW), immediately after the
load/specialization CPU spike (3.1 → 6.9 W), and then reports 0–9 mW for the remaining ~11 s —
during which the run performs 6,000 inferences at 2.14 ms. That is irreconcilable with
`enginemon`'s 173 GB and 27,784 ANE interrupts over an equivalent run. Two runs of the same
workload disagreeing by ~200× means **`powermetrics`' `ane_power` sampler cannot adjudicate
Core AI placement or state.**

**What stands (repeated and mutually consistent):**

- the compiled artifact contains **1 ANE region** (403 KB `ANE_region_0_0.mlir.bc`)
- **173 GB / 27,784 interrupts** of ANE traffic, and **0** under `cpuOnly`
- `--compute gpu` on the AOT bundle still reaches the ANE (placement is baked at compile time)
- latency: fast ~1.85–2.14 ms vs 4.31 ms for fp32 on the GPU

**What remains open:** the burst/sustained root cause. ANE power was the intended discriminator
and it is unreliable; going further needs the **private** ANE path (`_ANEClient` / the ANEForge
runtime the guide documents) rather than Core AI plus IOReport.

### Related roofline facts (from the same sources)

- **0.23 ms floor under any single dispatch**; dispatch latency is ~model-size-independent
  (42 ms/token sequential on a private-API LLM path, 11.3× better batched).
- **2 MB working-set threshold** on the roofline; efficiency ~0.37 pJ/FLOP at peak.
- The compiler **fuses a whole graph into a single program** — consistent with our 1 ANE region.

## Caveats

- **Numerics.** fp16 passes the zoo's embedding+retrieval gate (cos 0.9999589, err 1.58e-03,
  4/4 top-1, 0 flips) but fails the stricter **layer** gate, which is why the published bundle
  is fp32. These bundles are **placement probes**; promoting one to a shipped artifact would
  mean running the layer gate and a real retrieval benchmark first.
- **Retrieval evidence is a parity instrument, not a benchmark** (35 texts, 4 queries,
  12 documents).
- **Still segmented (mildly).** v3 emits **1 ANE region *and* MPSGraph delegates**, so the graph is
  still split across ANE and GPU. Full residency needs the structural recipe (BC1S layout,
  1×1 Conv2d projections, per-head attention with `bchq,bkhc->bkhq`, no fused SDPA) — and note
  that recipe keeps fp16, so it is a **performance** change, not a precision fix. The zoo's own
  measurement is that ANE-authoring is *not* faster in steady state and mainly **buys load
  time** — which we already have (55 ms).
- **One grid, one arch.** S=128 on h16g (M4). S=512 and other SoCs are untested.
- **`--compute` does not override an AOT bundle.** An fp16 AOT bundle uses the ANE under both
  `--compute neuralEngine` (101.6 GB moved) and `--compute gpu` (91.2 GB), while `--compute
  cpuOnly` drops to 0 interrupts — the compile-time choice is baked.

## Artifacts

- `bench/probe_ane_regions.py` — the dtype control probe (tiny ANE-shaped graph, fp16 vs fp32)
- `bench/export_granite_fp16_placement.py` — fp16 export + AOT compile + region count
- `bench/granite_ane_variants.py` — the v0–v3 residency sweep (in-memory patches; zoo file untouched)
- `bench/bench_ane_variants.py` — runtime benchmark under `tools/enginemon`
- `bench/gate_precision_report.py` — the zoo's full numerical + **retrieval** gate, on runtime dumps
- `bench/export_granite_w8_fp16.py` — w8 palettized weights + fp16 compute (PEP 723 header; `uv run`)
- `work/exports/granite-embedding-97m/w8fp16/s128/` — the 167 MB w8+fp16 bundle + `probe-record.json`
- `tools/granite-runner/` — extended with `--dump-embeddings PATH` (gate on runtime outputs) and
  `--dump-latencies PATH` (raw per-inference series, in acquisition order — the ordering is what
  distinguishes a one-way transition from noise)
- `work/lat/*.txt` — the raw latency series behind Step 7 (on disk, gitignored)
- `work/exports/granite-embedding-97m/ane-sweep/{v0..v3}/` — bundles + `sweep.json` + `bench.json`
  (on disk, gitignored: ~1.5 GB of regenerable bundles)
- `tools/enginemon/` — the unprivileged per-engine monitor used for every runtime number

## Upstream value

The published bundle can never use the ANE — it is fp32. An **fp16 sibling with three fp32-op
removals** runs on the ANE, is marginally faster, loads 2× faster, and draws ~125× less GPU
power. That is a concrete, reproducible recipe for the zoo's *"Not tested: the Neural Engine"*
row, and it reframes the fp16 decision: fp16 was rejected on layer-numerics, but the
*placement* consequence of fp32 was never measured.

---

## Measurements (generated)

> Generated from `results/measurements.json` by `bench/results_table.py`. **Do not hand-edit** — regenerate.
> Rows appear only when another row is genuinely comparable; `benchmark+split+scope+tiers+metric+unit`
> must agree. See `results/CONSISTENCY-PLAN.md` for why.

| id | model | placement | dtype | seq_len | metric | value | unit | latency_ms | latency_unit | provenance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tiny-ane-shaped-control-graph-1-1-conv2d-bc1s-channel-layernorm-ane-an | tiny ANE-shaped control graph (1×1 Conv2d, BC1S, channel LayerNorm) | ANE | fp16 | 128 | ANE regions (corrected, F-27) | 66 | ANE regions | — | — | ours |
| tiny-ane-shaped-control-graph-1-1-conv2d-bc1s-channel-layernorm-gpu-an | tiny ANE-shaped control graph (1×1 Conv2d, BC1S, channel LayerNorm) | GPU | fp32 | 128 | ANE regions (corrected, F-27) | 0 | ANE regions | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-ane-regions | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | ANE regions | 0 | ANE regions | — | — | ours |
| granite-embedding-97m-fp16-re-export-ane-ane-regions-as-reported-pre-f | Granite-Embedding-97M (fp16 re-export) | ANE | fp16 | 128 | ANE regions (as reported, pre-F-27) | 14 | ANE regions | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-ane-regions-2 | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | ANE regions | 0 | ANE regions | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-ane-moved | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | ANE moved | 0 | GB of ANE traffic | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-ane-interrupts | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | ANE interrupts | 0 | interrupts | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-gpu-power | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | GPU power | 10390 | mW | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-load-time | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | load time | 122 | ms | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-warm-median-latency | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | warm median latency | 4.33 | ms | 4.33 | per embedding (per inference) | ours |
| granite-embedding-97m-fp32-published-gpu-min-cosine | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | min cosine | 1 | cosine | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-max-abs-error | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | max abs error | 2.98e-07 | absolute error | — | — | ours |
| granite-embedding-97m-fp16-v0-as-is-ane-ane-regions | Granite-Embedding-97M (fp16 v0, as-is) | ANE | fp16 | 128 | ANE regions | 13 | ANE regions | — | — | ours |
| granite-embedding-97m-fp16-v0-as-is-ane-ane-moved | Granite-Embedding-97M (fp16 v0, as-is) | ANE | fp16 | 128 | ANE moved | 91.7 | GB of ANE traffic | — | — | ours |
| granite-embedding-97m-fp16-v0-as-is-ane-ane-interrupts | Granite-Embedding-97M (fp16 v0, as-is) | ANE | fp16 | 128 | ANE interrupts | 122832 | interrupts | — | — | ours |
| granite-embedding-97m-fp16-v0-as-is-ane-gpu-power | Granite-Embedding-97M (fp16 v0, as-is) | ANE | fp16 | 128 | GPU power | 333 | mW | — | — | ours |
| granite-embedding-97m-fp16-v0-as-is-ane-load-time | Granite-Embedding-97M (fp16 v0, as-is) | ANE | fp16 | 128 | load time | 87 | ms | — | — | ours |
| granite-embedding-97m-fp16-v0-as-is-ane-warm-median-latency | Granite-Embedding-97M (fp16 v0, as-is) | ANE | fp16 | 128 | warm median latency | 13.14 | ms | 13.14 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v0-as-is-ane-min-cosine | Granite-Embedding-97M (fp16 v0, as-is) | ANE | fp16 | 128 | min cosine | 1 | cosine | — | — | ours |
| granite-embedding-97m-fp16-v0-as-is-ane-max-abs-error | Granite-Embedding-97M (fp16 v0, as-is) | ANE | fp16 | 128 | max abs error | 0.00146 | absolute error | — | — | ours |
| granite-embedding-97m-fp16-v1-fp16-softmax-ane-ane-regions | Granite-Embedding-97M (fp16 v1, +fp16 softmax) | ANE | fp16 | 128 | ANE regions | 1 | ANE regions | — | — | ours |
| granite-embedding-97m-fp16-v1-fp16-softmax-ane-ane-moved | Granite-Embedding-97M (fp16 v1, +fp16 softmax) | ANE | fp16 | 128 | ANE moved | 87.7 | GB of ANE traffic | — | — | ours |
| granite-embedding-97m-fp16-v1-fp16-softmax-ane-ane-interrupts | Granite-Embedding-97M (fp16 v1, +fp16 softmax) | ANE | fp16 | 128 | ANE interrupts | 15050 | interrupts | — | — | ours |
| granite-embedding-97m-fp16-v1-fp16-softmax-ane-gpu-power | Granite-Embedding-97M (fp16 v1, +fp16 softmax) | ANE | fp16 | 128 | GPU power | 125 | mW | — | — | ours |
| granite-embedding-97m-fp16-v1-fp16-softmax-ane-load-time | Granite-Embedding-97M (fp16 v1, +fp16 softmax) | ANE | fp16 | 128 | load time | 271 | ms | — | — | ours |
| granite-embedding-97m-fp16-v1-fp16-softmax-ane-warm-median-latency | Granite-Embedding-97M (fp16 v1, +fp16 softmax) | ANE | fp16 | 128 | warm median latency | 5.18 | ms | 5.18 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v1-fp16-softmax-ane-min-cosine | Granite-Embedding-97M (fp16 v1, +fp16 softmax) | ANE | fp16 | 128 | min cosine | 1 | cosine | — | — | ours |
| granite-embedding-97m-fp16-v1-fp16-softmax-ane-max-abs-error | Granite-Embedding-97M (fp16 v1, +fp16 softmax) | ANE | fp16 | 128 | max abs error | 0.0014 | absolute error | — | — | ours |
| granite-embedding-97m-fp16-v2-f16-scale-ane-ane-regions | Granite-Embedding-97M (fp16 v2, +f16 scale) | ANE | fp16 | 128 | ANE regions | 1 | ANE regions | — | — | ours |
| granite-embedding-97m-fp16-v2-f16-scale-ane-ane-moved | Granite-Embedding-97M (fp16 v2, +f16 scale) | ANE | fp16 | 128 | ANE moved | 87.7 | GB of ANE traffic | — | — | ours |
| granite-embedding-97m-fp16-v2-f16-scale-ane-ane-interrupts | Granite-Embedding-97M (fp16 v2, +f16 scale) | ANE | fp16 | 128 | ANE interrupts | 14848 | interrupts | — | — | ours |
| granite-embedding-97m-fp16-v2-f16-scale-ane-gpu-power | Granite-Embedding-97M (fp16 v2, +f16 scale) | ANE | fp16 | 128 | GPU power | 127 | mW | — | — | ours |
| granite-embedding-97m-fp16-v2-f16-scale-ane-load-time | Granite-Embedding-97M (fp16 v2, +f16 scale) | ANE | fp16 | 128 | load time | 55 | ms | — | — | ours |
| granite-embedding-97m-fp16-v2-f16-scale-ane-warm-median-latency | Granite-Embedding-97M (fp16 v2, +f16 scale) | ANE | fp16 | 128 | warm median latency | 5.24 | ms | 5.24 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v2-f16-scale-ane-min-cosine | Granite-Embedding-97M (fp16 v2, +f16 scale) | ANE | fp16 | 128 | min cosine | 1 | cosine | — | — | ours |
| granite-embedding-97m-fp16-v2-f16-scale-ane-max-abs-error | Granite-Embedding-97M (fp16 v2, +f16 scale) | ANE | fp16 | 128 | max abs error | 0.0014 | absolute error | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-ane-regions | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | ANE regions | 1 | ANE regions | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-ane-moved | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | ANE moved | 87.7 | GB of ANE traffic | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-ane-interrupts | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | ANE interrupts | 13472 | interrupts | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-gpu-power | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | GPU power | 83 | mW | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-load-time | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | load time | 55 | ms | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-warm-median-latency | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | warm median latency | 4 | ms | 4 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-min-cosine | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | min cosine | 1 | cosine | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-max-abs-error | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | max abs error | 0.00158 | absolute error | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-min-cosine-2 | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | min cosine | 1 | cosine | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-max-abs-error-2 | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | max abs error | 2.98e-07 | absolute error | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-norm-error | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | norm error | 1.89e-07 | relative norm error | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-clear-pair-flips | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | clear pair flips | 0 | document pairs inverted | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-worst-score-error | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | worst score error | 1.64e-07 | score error | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-min-cosine-2 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | min cosine | 1 | cosine | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-max-abs-error-2 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | max abs error | 0.00158 | absolute error | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-norm-error | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | norm error | 0.000592 | relative norm error | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-clear-pair-flips | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | clear pair flips | 0 | document pairs inverted | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-worst-score-error | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | worst score error | 0.0022 | score error | — | — | ours |
| granite-embedding-97m-fp16-v2-f16-scale-ane-warm-median-latency-2 | Granite-Embedding-97M (fp16 v2, +f16 scale) | ANE | fp16 (fp32 pooling) | 128 | warm median latency | 5.24 | ms | 5.24 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v2-f16-scale-ane-gpu-power-2 | Granite-Embedding-97M (fp16 v2, +f16 scale) | ANE | fp16 (fp32 pooling) | 128 | GPU power | 127 | mW | — | — | ours |
| granite-embedding-97m-fp16-v2-f16-scale-ane-max-abs-error-2 | Granite-Embedding-97M (fp16 v2, +f16 scale) | ANE | fp16 (fp32 pooling) | 128 | max abs error | 0.0014 | absolute error | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-warm-median-latency-2 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | warm median latency | 4 | ms | 4 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-gpu-power-2 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | GPU power | 83 | mW | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-max-abs-error-3 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | max abs error | 0.00158 | absolute error | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-storage-element-count | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | storage element count | 97457544 | Float32 elements | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-storage-element-count | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | storage element count | 97457542 | Float16 elements | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-storage-element-count-2 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | storage element count | 2 | Float32 elements | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-ane-moved-2 | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | ANE moved | 0 | GB of ANE traffic | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-ane-interrupts-2 | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | ANE interrupts | 0 | interrupts | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-gpu-power-2 | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | GPU power | 8025 | mW | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-load-time-2 | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | load time | 797 | ms | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-warm-median-latency-2 | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | warm median latency | 4.31 | ms | 4.31 | per embedding (per inference) | ours |
| granite-embedding-97m-fp32-published-gpu-min-cosine-3 | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | min cosine | 1 | cosine | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-max-abs-error-3 | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | max abs error | 2.98e-07 | absolute error | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-bundle-size | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | bundle size | 390 | MB | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-ane-moved-2 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | ANE moved | 87.7 | GB of ANE traffic | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-ane-interrupts-2 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | ANE interrupts | 13730 | interrupts | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-gpu-power-3 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | GPU power | 62.7 | mW | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-load-time-2 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | load time | 257 | ms | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-warm-median-latency-3 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | warm median latency | 4.05 | ms | 4.05 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-min-cosine-3 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | min cosine | 1 | cosine | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-max-abs-error-4 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | max abs error | 0.00158 | absolute error | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-bundle-size | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | bundle size | 195 | MB | — | — | ours |
| granite-embedding-97m-w8-fp16-ane-ane-moved | Granite-Embedding-97M (w8 + fp16) | ANE | int8-affine weights + fp16 compute | 128 | ANE moved | 59.9 | GB of ANE traffic | — | — | ours |
| granite-embedding-97m-w8-fp16-ane-ane-interrupts | Granite-Embedding-97M (w8 + fp16) | ANE | int8-affine weights + fp16 compute | 128 | ANE interrupts | 83050 | interrupts | — | — | ours |
| granite-embedding-97m-w8-fp16-ane-gpu-power | Granite-Embedding-97M (w8 + fp16) | ANE | int8-affine weights + fp16 compute | 128 | GPU power | 241.6 | mW | — | — | ours |
| granite-embedding-97m-w8-fp16-ane-load-time | Granite-Embedding-97M (w8 + fp16) | ANE | int8-affine weights + fp16 compute | 128 | load time | 2131 | ms | — | — | ours |
| granite-embedding-97m-w8-fp16-ane-warm-median-latency | Granite-Embedding-97M (w8 + fp16) | ANE | int8-affine weights + fp16 compute | 128 | warm median latency | 19.48 | ms | 19.48 | per embedding (per inference) | ours |
| granite-embedding-97m-w8-fp16-ane-min-cosine | Granite-Embedding-97M (w8 + fp16) | ANE | int8-affine weights + fp16 compute | 128 | min cosine | 0.9994 | cosine | — | — | ours |
| granite-embedding-97m-w8-fp16-ane-max-abs-error | Granite-Embedding-97M (w8 + fp16) | ANE | int8-affine weights + fp16 compute | 128 | max abs error | 0.00609 | absolute error | — | — | ours |
| granite-embedding-97m-w8-fp16-ane-bundle-size | Granite-Embedding-97M (w8 + fp16) | ANE | int8-affine weights + fp16 compute | 128 | bundle size | 167 | MB | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-ane-regions-corrected-f-27 | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | ANE regions (corrected, F-27) | 0 | ANE regions | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-ane-regions-as-reported-pre-f | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | ANE regions (as reported, pre-F-27) | 0 | ANE regions | — | — | ours |
| granite-embedding-97m-fp16-v0-as-is-ane-ane-regions-corrected-f-27 | Granite-Embedding-97M (fp16 v0, as-is) | ANE | fp16 | 128 | ANE regions (corrected, F-27) | 13 | ANE regions | — | — | ours |
| granite-embedding-97m-fp16-v0-as-is-ane-ane-regions-as-reported-pre-f | Granite-Embedding-97M (fp16 v0, as-is) | ANE | fp16 | 128 | ANE regions (as reported, pre-F-27) | 14 | ANE regions | — | — | ours |
| granite-embedding-97m-fp16-v1-v2-v3-ane-ane-regions-corrected-f-27 | Granite-Embedding-97M (fp16 v1 / v2 / v3) | ANE | fp16 | 128 | ANE regions (corrected, F-27) | 1 | ANE regions | — | — | ours |
| granite-embedding-97m-fp16-v1-v2-v3-ane-ane-regions-as-reported-pre-f | Granite-Embedding-97M (fp16 v1 / v2 / v3) | ANE | fp16 | 128 | ANE regions (as reported, pre-F-27) | 2 | ANE regions | — | — | ours |
| granite-embedding-97m-w8-fp16-ane-ane-regions-corrected-f-27 | Granite-Embedding-97M (w8 + fp16) | ANE | int8-affine weights + fp16 compute | 128 | ANE regions (corrected, F-27) | 13 | ANE regions | — | — | ours |
| granite-embedding-97m-w8-fp16-ane-ane-regions-as-reported-pre-f-27 | Granite-Embedding-97M (w8 + fp16) | ANE | int8-affine weights + fp16 compute | 128 | ANE regions (as reported, pre-F-27) | 14 | ANE regions | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-bundle-component-size-r | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | bundle component size: resources.bin (weights) | 194917488 | bytes | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-bundle-component-size-a | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | bundle component size: ANE region .mlir.bc | 403651 | bytes | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-bundle-component-size-m | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | bundle component size: MPSGraph original_model_0.mpsgraph | 121802 | bytes | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-bundle-component-size-m-2 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | bundle component size: MPSGraph specialized_model_1.mpsgraph | 99715 | bytes | — | — | ours |
| granite-embedding-97m-fp16-v0-as-is-ane-ane-regions-2 | Granite-Embedding-97M (fp16 v0, as-is) | ANE | fp16 | 128 | ANE regions | 13 | ANE regions | — | — | ours |
| granite-embedding-97m-fp16-v0-as-is-ane-converged-median-latency-4000 | Granite-Embedding-97M (fp16 v0, as-is) | ANE | fp16 | 128 | converged median latency (4000 iters) | 13.19 | ms | 13.19 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-ane-regions-2 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | ANE regions | 1 | ANE regions | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-converged-median-latenc | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | converged median latency (4000 iters) | 4.6 | ms | 4.6 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-median-latency | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | median latency | 4.6 | ms | 4.6 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-min-latency | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | min latency | 1.85 | ms | 1.85 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-gpu-power-4 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | GPU power | 75 | mW | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-gpu-median-latency | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | GPU | fp16 | 128 | median latency | 5.52 | ms | 5.52 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-gpu-min-latency | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | GPU | fp16 | 128 | min latency | 4.58 | ms | 4.58 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-gpu-gpu-power | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | GPU | fp16 | 128 | GPU power | 4124 | mW | — | — | ours |
| granite-embedding-97m-fp32-published-gpu-median-latency | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | median latency | 4.31 | ms | 4.31 | per embedding (per inference) | ours |
| granite-embedding-97m-fp32-published-gpu-min-latency | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | min latency | 4.17 | ms | 4.17 | per embedding (per inference) | ours |
| granite-embedding-97m-fp32-published-gpu-gpu-power-3 | Granite-Embedding-97M (fp32 published) | GPU | fp32 | 128 | GPU power | 8025 | mW | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-median-latency-another | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | median latency (another run) | 2.17 | ms | 2.17 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-warm-median-latency-ide | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | warm median latency (identical repeat run) | 2.14 | ms | 2.14 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-warm-median-latency-ide-2 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | warm median latency (identical repeat run) | 2.15 | ms | 2.15 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-warm-median-latency-ide-3 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | warm median latency (identical repeat run) | 2.15 | ms | 2.15 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-warm-median-latency-ide-4 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | warm median latency (identical repeat run) | 2.17 | ms | 2.17 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-warm-median-latency-ide-5 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | warm median latency (identical repeat run) | 2.4 | ms | 2.4 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-warm-median-latency-ide-6 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | warm median latency (identical repeat run) | 3.38 | ms | 3.38 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-warm-median-latency-ide-7 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | warm median latency (identical repeat run) | 3.77 | ms | 3.77 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-warm-median-latency-ide-8 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | warm median latency (identical repeat run) | 4.26 | ms | 4.26 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-warm-median-latency-ide-9 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | warm median latency (identical repeat run) | 4.6 | ms | 4.6 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-warm-median-latency-ide-10 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | warm median latency (identical repeat run) | 4.9 | ms | 4.9 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-latency-fast-state | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | latency (fast state) | 1.85 | ms (reported range 1.85-2.25 ms; value is the lower bound) | 1.85 | per inference | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-effective-ane-bandwidth | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | effective ANE bandwidth (fast state) | 31 | GB/s (approximate, as reported) | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-latency-slow-state | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | latency (slow state) | 4.75 | ms (approximate, as reported) | 4.75 | per inference | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-effective-ane-bandwidth-2 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | effective ANE bandwidth (slow state) | 14.5 | GB/s (approximate, as reported) | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-transformer-linear-weig | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | transformer linear weight size (48 linears, fp16) | 56.6 | MB | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-ane-traffic-per-inferen | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | ANE traffic per inference | 57 | MB (reported range 57-63 MB per inference; value is the lower bound) | — | — | ours |
| apple-m4-ane-ane-on-chip-scratchpad-size | Apple M4 ANE | ANE | — | 128 | on-chip scratchpad size | 32 | MB (reported as ~32 MB) | — | — | vendor (Apple) |
| apple-m4-ane-literature-ane-working-set-threshold-for-degradation | Apple M4 ANE (literature) | ANE | — | 128 | working-set threshold for degradation | 24 | MB | — | — | third-party (maderix; Orion SRAM annotation) |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-ane-traffic | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | ANE traffic | 173 | GB | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-ane-interrupts-3 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | ANE interrupts | 27784 | interrupts | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-ane-regions-3 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | ANE regions | 1 | ANE regions | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-min-cosine-4 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | min cosine | 1 | cosine | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-clear-pair-flips-2 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | clear pair flips | 0 | document pairs inverted | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-bundle-size-2 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | bundle size | 195 | MB | — | — | ours |
| granite-embedding-97m-w8-fp16-ane-ane-regions | Granite-Embedding-97M (w8 + fp16) | ANE | int8-affine weights + fp16 compute | 128 | ANE regions | 13 | ANE regions | — | — | ours |
| granite-embedding-97m-w8-fp16-ane-min-cosine-2 | Granite-Embedding-97M (w8 + fp16) | ANE | int8-affine weights + fp16 compute | 128 | min cosine | 0.9994 | cosine | — | — | ours |
| granite-embedding-97m-w8-fp16-ane-clear-pair-flips | Granite-Embedding-97M (w8 + fp16) | ANE | int8-affine weights + fp16 compute | 128 | clear pair flips | 0 | document pairs inverted | — | — | ours |
| granite-embedding-97m-w8-fp16-ane-bundle-size-2 | Granite-Embedding-97M (w8 + fp16) | ANE | int8-affine weights + fp16 compute | 128 | bundle size | 167 | MB | — | — | ours |
| granite-embedding-97m-w6-fp16-ane-ane-regions | Granite-Embedding-97M (w6 + fp16) | ANE | w6 weights + fp16 | 128 | ANE regions | 14 | ANE regions | — | — | ours |
| granite-embedding-97m-w6-fp16-ane-min-cosine | Granite-Embedding-97M (w6 + fp16) | ANE | w6 weights + fp16 | 128 | min cosine | 0.9984 | cosine | — | — | ours |
| granite-embedding-97m-w6-fp16-ane-clear-pair-flips | Granite-Embedding-97M (w6 + fp16) | ANE | w6 weights + fp16 | 128 | clear pair flips | 1 | document pairs inverted | — | — | ours |
| granite-embedding-97m-w6-fp16-ane-bundle-size | Granite-Embedding-97M (w6 + fp16) | ANE | w6 weights + fp16 | 128 | bundle size | 160 | MB | — | — | ours |
| granite-embedding-97m-w4-fp16-ane-ane-regions | Granite-Embedding-97M (w4 + fp16) | ANE | w4 weights + fp16 | 128 | ANE regions | 0 | ANE regions | — | — | ours |
| granite-embedding-97m-w4-fp16-ane-min-cosine | Granite-Embedding-97M (w4 + fp16) | ANE | w4 weights + fp16 | 128 | min cosine | 0.9622 | cosine | — | — | ours |
| granite-embedding-97m-w4-fp16-ane-clear-pair-flips | Granite-Embedding-97M (w4 + fp16) | ANE | w4 weights + fp16 | 128 | clear pair flips | 16 | document pairs inverted | — | — | ours |
| granite-embedding-97m-w4-fp16-ane-bundle-size | Granite-Embedding-97M (w4 + fp16) | ANE | w4 weights + fp16 | 128 | bundle size | 153 | MB | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-median-latency-2 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | median latency | 2.14 | ms | 2.14 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-ane-power | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | ANE power | 1914 | mW | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-gpu-power-5 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | GPU power | 361.4 | mW | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-cpu-power | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | CPU power | 986.9 | mW | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-gpu-median-latency-2 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | GPU | fp16 | 128 | median latency | 1.94 | ms | 1.94 | per embedding (per inference) | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-gpu-ane-power | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | GPU | fp16 | 128 | ANE power | 1792 | mW | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-gpu-gpu-power-2 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | GPU | fp16 | 128 | GPU power | 445.8 | mW | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-gpu-cpu-power | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | GPU | fp16 | 128 | CPU power | 1152 | mW | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-cpuonly-ane-power | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | cpuOnly | fp16 | 128 | ANE power | 8 | mW | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-cpuonly-gpu-power | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | cpuOnly | fp16 | 128 | GPU power | 2 | mW | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-cpuonly-cpu-power | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | cpuOnly | fp16 | 128 | CPU power | 714.2 | mW | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-ane-power-2 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | ANE power | 1914 | mW (validated parser, 500 ms, averaged) | — | — | ours |
| granite-embedding-97m-fp16-v3-fp16-pooling-ane-ane-power-3 | Granite-Embedding-97M (fp16 v3, +fp16 pooling) | ANE | fp16 | 128 | ANE power | 0 | mW (reported as ~0 mW for ~11 of 13 s; 400 samples, 200 ms, full series) | — | — | ours |
| zoo-w8-variant-of-granite-embedding-97m-shipped-fp32-compute-none-min | zoo w8 variant of Granite-Embedding-97M (shipped, fp32 compute) | — | int8-affine weights + fp32 compute | 128 | min cosine | 0.9994 | cosine | — | — | third-party (zoo shipped w8 variant record) |
| zoo-w8-variant-of-granite-embedding-97m-shipped-fp32-compute-none-max | zoo w8 variant of Granite-Embedding-97M (shipped, fp32 compute) | — | int8-affine weights + fp32 compute | 128 | max abs error | 0.00567 | absolute error | — | — | third-party (zoo shipped w8 variant record) |
| apple-ane-roofline-from-the-guide-s-cited-sources-ane-single-dispatch | Apple ANE roofline (from the guide's cited sources) | ANE | — | 128 | single-dispatch latency floor | 0.23 | ms | — | — | third-party (roofline sources cited in the guide) |
| apple-ane-roofline-from-the-guide-s-cited-sources-ane-working-set-thre | Apple ANE roofline (from the guide's cited sources) | ANE | — | 128 | working-set threshold | 2 | MB | — | — | third-party (roofline sources cited in the guide) |
| apple-ane-roofline-from-the-guide-s-cited-sources-ane-peak-efficiency | Apple ANE roofline (from the guide's cited sources) | ANE | — | 128 | peak efficiency | 0.37 | pJ/FLOP | — | — | third-party (roofline sources cited in the guide) |
