# What's new — 2026-10-26 (round 3: the integer lanes, and the door)

Same status key: **NEW** = we could not find it published · **EXT** = extends published work · **KNOWN** = already public.
Earlier rounds follow below, newest first.

| # | Finding | Status | Evidence |
|---|---|---|---|
| 15 | **First published int8 and fp32 lane numbers for the M5 Max NAX tensor units** — hand-written MSL `matmul2d`, bit-exact against exact-integer oracles: **int8 55.2 TF @4096³ = 1.74× the fp16/fp8 band** (independently matches a published A19 ratio of 1.8×), **fp32 14.0 TF** @4096³, decode (M=1, 64-row padded tile) i8 0.0679 ms @K4096. Measured in a loaded-box window and declared as upper bounds. | **NEW** | [`results/EXP-037-fp8-nax/results/lane_matrix-20261026T1509Z.tsv`](results/EXP-037-fp8-nax/results/lane_matrix-20261026T1509Z.tsv) · [`README`](results/EXP-037-fp8-nax/README.md) |
| 16 | **fp8 (`metal_fp8_e4m3_format`) executes natively on NAX** — 32.0 TF @2048³, bit-exact 24/24, energy at parity-with-noise vs fp16; it **requires `-std=metal4.1`** (4.0 rejects the type — measured), and the 4.1 gate is fp8-specific, not device-tensor-general (the f32/f16 arms compile at 4.0 too). | **NEW** | [`results/EXP-037-fp8-nax/results/fp8_matrix-20261026T1356Z.tsv`](results/EXP-037-fp8-nax/results/fp8_matrix-20261026T1356Z.tsv) |
| 17 | **The IOKit side door into the ANE, mapped** — direct-path round-trips 3.2–7.1 µs (success), error returns from 0.6 µs, and the submit gate is **CLOSED and load-blind** (36/36 cells): the door answers whether the box is busy, not how busy; side-door injection observed 0.5–7.3 µs (n=141). | **NEW** | [`results/EXP-033-door-map/README.md`](results/EXP-033-door-map/README.md) · [`raw sweep`](results/EXP-036-side-door-inject/raw/probe10_sweep_run1.jsonl) |
| 18 | **int8 flips sign between fleets**: 4.8× *slower* than fp16 on the M4 mini's ANE (round-1 finding) vs **1.74× faster** on the M5 Max's GPU tensor lane — quantization advice does not transfer between engines, even within one vendor generation. | **EXT** — extends our own M4 result | [`results/EXP-005-ane-residency/README.md`](results/EXP-005-ane-residency/README.md) · [`lane_matrix tsv`](results/EXP-037-fp8-nax/results/lane_matrix-20261026T1509Z.tsv) |
| 19 | **A single consolidated lane reference, gated** — every lane measured on this fleet in one table, per surface, each cell carrying window·metric-convention·instrument·capture-link; 13 contaminated sets quarantined (kept, stamped, excluded); 9 open flags with named deciders. | **NEW** (process; published because drift is the failure mode it prevents) | [`knowledge/ane/16-neural-accelerators.md`](knowledge/ane/16-neural-accelerators.md) |

---

# What's new — 2026-10-10 (round 2: the GPU Neural Accelerators, and the tooling memory)

This mirror is the **distilled** public slice of a private Apple-silicon reverse-engineering
corpus (private paths scrubbed, evidence kept). This page is the one-screen summary: what the
latest round found, and — honestly — **what is new versus already public**. Full priors are in
[`knowledge/ane/SOURCES.md`](knowledge/ane/SOURCES.md) ("Novelty check 2026-10-10").

## Status key
**NEW** = we could not find it published · **EXT** = extends published work · **KNOWN** = already public.

## The findings

| # | Finding | Status | Evidence |
|---|---|---|---|
| 1 | A **cross-chip arch identity**: the Core AI compiler target is `h17c` on an M5 Max and `h16g` on an M4 mini, while the older private `_ANEDeviceInfo` selector returns the `g` form on both (`h17g`/`h16g`) — so it agrees on the M4 and **diverges on the M5 Max**. | **EXT** — the rule is public, and the **M4 half is our own merged PR** ([coreai-model-zoo #36](https://github.com/john-rocky/coreai-model-zoo/pull/36)); new: the M5 Max `h17c` target + the selector divergence | [`results/EXP-028-apple-tracer/results/e6_arch_surface_reconcile.txt`](results/EXP-028-apple-tracer/results/e6_arch_surface_reconcile.txt) |
| 2 | **Core AI's on-disk specialization cache decoded** — the `~/Library/Caches/coreai-cache` layout (`modelHash` per model vs `optsHash` = a pure function of the compute-unit options). Nothing public documents these bytes. | **NEW** | [`results/EXP-026-ane-kitchen/results/coreai_cache_format.md`](results/EXP-026-ane-kitchen/results/coreai_cache_format.md) |
| 3 | **The cached `mpsgraph` bytecode printed as readable MLIR** — a stub dialect plugin + a bytecode rewrite recover the op graph, region functions, shapes and `mps.aneArch`/`aneRegionsSHA`. | **EXT** — "MPSGraph is MLIR bytecode" is public (Apple's LLVM RFC, `mpsgraphtool`); **new**: the private `aicode`/`placement` dialects and the printing technique | [`results/EXP-026-ane-kitchen/results/p2b_model_src_ir.txt`](results/EXP-026-ane-kitchen/results/p2b_model_src_ir.txt) |
| 4 | **`PMP0/SOC-NI9 "ANEXL U"` is a lane-exclusive, calibrated ANE activity counter** — 0 in every idle/GPU/CPU window, ~19.6k under ANE work. The channel is known; its **exclusivity** is not. | **NEW as a discriminator** | [`results/EXP-027-nax/results/p27_anpos_promote.txt`](results/EXP-027-nax/results/p27_anpos_promote.txt) |
| 5 | The `PMP0` **`ANE-DCS-BW` floor-residency channel is *not* ANE-specific** (reads higher at idle than under ANE load), and the **`Fast-Die CE` utilization histogram reads 0** even during confirmed ANE work — so the channel public tools use for "ANE utilization" is dead on this box. | **NEW** (negative results) | [`p27_anpos_promote.txt`](results/EXP-027-nax/results/p27_anpos_promote.txt) |
| 6 | **Apple's on-device Foundation Model uses the Neural Engine** — measured with the calibrated exclusive lens, unprivileged: `ANEXL U` reads 0 at idle and 10,862 across a 25-call `fm` burst. (Lane mix: ANE-active; no GPU engagement above idle.) | **NEW method** (the fact was known via xctrace; the repeatable unprivileged measurement is new) | [`results/EXP-002-apple-fm-baseline/results/fm_lane_audit.txt`](results/EXP-002-apple-fm-baseline/results/fm_lane_audit.txt) |
| 7 | The **ANE↔GPU "direct link" carries data, both directions** — a GPU kernel writes an IOSurface and signals; the ANE-side event wrapper waits; content verified every iteration. 500/500 both ways at ~123 µs / ~136 µs, unprivileged. | **NEW** (the wire the ANE uses, driven end-to-end with data; putting a live ANE program on the other end is still blocked) | [`results/EXP-025-ane-gpu-sync/results/chain_harness.txt`](results/EXP-025-ane-gpu-sync/results/chain_harness.txt) |

A correction note for finding #1 is filed upstream:
<https://github.com/sbryngelson/ane-guide/issues/1>.

## What this mirror is (and is not)
- **Is:** measured numbers, the failure corpus, and the instruments, with every claim carrying its
  command and its caveats. The claim layer is machine-checkable — see
  [`PUBLIC-OPENCLAIMS.md`](PUBLIC-OPENCLAIMS.md) (699 claims, 824 provenance events, 0 invalid).
- **Is not:** vendor claims, or a promise that any of the private/documented Apple interfaces are
  stable. Where a claim is an AI's check rather than a human's, it says so.

Start at [`README.md`](README.md) and [`PUBLIC-INDEX.md`](PUBLIC-INDEX.md).

---

# Round 2 — same day, the GPU side (published as it happened)

Same status key: **NEW** = we could not find it published · **EXT** = extends published work · **KNOWN** = already public.

| # | Finding | Status | Evidence |
|---|---|---|---|
| 8 | **The widely-repeated "M5 multi-tile `matmul2d` silently no-ops — Apple compiler regression" is REFUTED on this box.** Third-party MetalHLO runs all 8 of its GEMM benchmarks correct against MLX, **including 4096x4096** (2048 threadgroups, cooperative-tensor MPP path), through the **legacy** pipeline with MSL 4.0. Our own no-op was a *usage* artifact (device destination, wrong accessor, MSL 4.1). | **NEW as a correction** (the failure is discussed publicly; the refutation is ours) | [`results/EXP-029-nax-crosslane/README.md`](results/EXP-029-nax-crosslane/README.md) |
| 9 | **Measured NAX lane matrix on M5 Max** — NAX (MPP `gemm_loop`) **2.26x faster than the shader/SIMT path at 4096^2**, ~2.0x less GPU energy for the same work, and **all three GPU datapaths collapse to ~0.43 ms at decode (M=1)**. | **NEW** (vendor material claims NAX is faster; no NAX-vs-SIMT-with-energy matrix that we could find) | [`results/EXP-029-nax-crosslane/results/NAX-LANE-MATRIX.md`](results/EXP-029-nax-crosslane/results/NAX-LANE-MATRIX.md) |
| 10 | **Engine comparison on identical GEMMs (fp16, K=N=4096)**: GPU beats the ANE **10.2x / 7.3x / 5.4x** at M = 1 / 512 / 2048 wall-clock — including decode. A **bare `matmul` does reach the ANE** at 2048^3 (refining the older "Linear falls back off-ANE" guidance), while the **1x1-conv form of the same GEMM is 2.1x slower** on the ANE. | **NEW** (measured); **KNOWN** that the ANE prefers conv shapes | [`results/EXP-029-nax-crosslane/docs/NAX-ACTIVATION-AND-MEMORY.md`](results/EXP-029-nax-crosslane/docs/NAX-ACTIVATION-AND-MEMORY.md) |
| 11 | **Unprivileged, symmetric lane attribution for one workload**: the ANE arm shows **GPU Energy 0.00 mJ with `ANEXL U` = 896**; the GPU arm shows **`ANEXL U` = 0**. | **EXT** — extends finding #4 (the ANEXL calibration) | [`NAX-LANE-MATRIX.md`](results/EXP-029-nax-crosslane/results/NAX-LANE-MATRIX.md) |
| 12 | **Measurement hazards, measured** (they invalidate joules if ignored): GPU idle power swings **25 -> 104 mW inside 30 s**; this machine's only "display" is the **screen-share virtual display** (no physical monitor) and `WindowServer` exists only while sharing, so the **headless floor is ~0-3 mW vs 27-85 mW while sharing**; and the `DISP*/DISPEXT*/VDD*` "RT" counters are **free-running ~24 MHz** (measured at 23.99 MHz with *no display attached*), so they are **not** display/activity signals. | **NEW** (the free-running-counter trap family was documented for `ANE_*_TRIG`; `DISP*` is new) | [`results/EXP-029-nax-crosslane/results/QUIET-STATE.md`](results/EXP-029-nax-crosslane/results/QUIET-STATE.md) |
| 13 | **A locale hazard that silently corrupts power data**: with `LANG=fr_FR`, Apple CLIs print comma decimals (`9,1`); the shared rail parser matched only `[\\d.]+`, so localized samples were **dropped without error**. Fixed and self-tested. | **NEW** (our fix; the bug class is generic) | [`bench/_power.py`](bench/_power.py) · [`tools/publish/push-mirror.sh`](tools/publish/push-mirror.sh) |
| 14 | **An instrument registry with a gate** — 147 tools indexed across five locations with a *capability* map (which instrument is canonical for timing / joules / lane activity / matmul2d ladders / placement / ledger), plus a one-command gate set that **fails** when a tool exists on disk unregistered. | **NEW** (process; published because anyone with the same problem can use it) | [`tools/TOOLS.md`](tools/TOOLS.md) · [`tools/registry.py`](tools/registry.py) |

**What is published vs private in round 2 (so a reader knows what they cannot see):** the mirror
carries the **evidence and the instruments** — `bench/` in full (including `.py`/`.m`), `tools/`,
`knowledge/`, and `results/**` as `.md`/`.json`/`.txt`/`.sh`. **Private-only:** the per-experiment
`results/**/harness/*.{m,metal,c,h,py}` sources, the gzipped raw captures, `repos/`, `models/`, and
the agent rule files under `.omp/`.
