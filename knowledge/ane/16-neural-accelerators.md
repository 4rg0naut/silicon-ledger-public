# 16 — Neural Accelerators (M5/M5 Max): rates, ceilings, measurement status (2026-10-06)

Harvested from primary sources fetched 2026-10-06 (pins: SOURCES TZAKHARKO-NA,
APPLE-MLX-M5, PAPER-ANE-RE; raw in results/EXP-024-engine-attribution/raw/research-2026-10-06/).
Confidence tags as in file 10. **[C]** = credible external, **[V]** = measured by us.

## Measured per-core rates (A19, 5 GPU cores, timing-derived) **[C]**

Zakharko A19 GPU benchmark (iPhone 17 Pro class; NA exposed through MSL tensor ops,
"not directly exposed to developers"):

| op | A19 5-core measured | rate/core/cycle | iso-clock vs A18 |
| --- | --- | --- | --- |
| SIMD FP32 | 1880 GFLOPS | — | 1× |
| SIMD FP16 | 3200 GFLOPS | — | ~0.7× |
| Matrix FP16 (fp16/fp32 accum) | 7500 GFLOPS | **1024 FLOPS/core/c** | **~4×** |
| Matrix INT8 (int32 accum) | 13500 GFLOPS | ~2048 OPS/core/c (caveats) | ~7.5× |

- Matrix ≥ SIMD×2.3 at same core count → NA is a real second datapath, ~4× on fp16 MMA.
- **Optimal tile ≥ 32×32** for all tested formats.
- Works on Xcode 26.1/26.x stable **[C]** — our R8 matmul2d multi-tile no-op was therefore
  *attributed* to a 27.0-beta GPUCompiler (metalfe-32023) regression.
  **CORRECTED 2026-10-10 (API-170): that attribution does not survive testing.** Multi-tile MPP
  matmul2d works on this exact box/OS: the vendored MetalHLO runs all 8 of its GEMM benchmarks
  correct against MLX, including 4096x4096 on the cooperative-tensor MPP path - through the LEGACY
  pipeline and MSL 4.0. The R8 no-op was a usage artifact of the hand-rolled probes (device
  destination, wrong accessor names, MSL 4.1), not an Apple silicon/compiler defect.

## Ceiling arithmetic for C8 re-audit **[C-formula + V-measured count]**

**The NAX count is the GPU-core count — 1 GPU core carries 1 Neural Accelerator** (BaseRT,
arXiv:2607.19438: "every core carries a dedicated Neural Accelerator"; SOURCES.md). NAX is a second
datapath **inside each GPU core**, NOT a separate engine and NOT an ANE variant.

Measured count on this box **[V]**: `system_profiler`/`ioreg` → **40 GPU cores** (Mac17,14, 18 CPU
cores, Metal 4) → **40 NAX units**.

NA fp16 ceiling = N_NAX × 1024 FLOPS/core/cycle × clock:
- 40 × 1024 × ~1.46–1.8 GHz → **~60–74 TFLOPS fp16** (~120–147 TOPS int8 at the int8 ×2 rate).
- Apple's marketing ~70 TFLOPS fp16 sits inside that band — i.e. the marketing number and the
  per-core rate are **consistent once the count is the GPU-core count**.

**CORRECTION (2026-10-10):** the earlier "HAL compiler-suffix count (h17c = 32)" reading of N was
wrong for NAX — `h17c` is this machine's **ANE** architecture name (`mps.aneArch`, API-138), so 32
was never a NAX unit count. Use **40** (GPU cores) for NAX ceilings and state the clock band; do not
mix an ANE-derived count into a GPU-datapath ceiling.

## Apple's own methodology (MLX M5 post) **[C]**

TTFT A/B only (throughput deltas prefill 3.9–6.4× via NA-routed GEMMs; same family as our
BaseRT-NA row). No counters, no per-engine energy. Nothing to adopt beyond the A/B shape
already in our C6 protocol.

## Measurement status on our silicon

- Unprivileged IOReport: no NA-specific channel at any level (file 10 Q1/Q6) **[V]**.
- Sudo powermetrics: 5 GPU keys only, no NA breakdown **[V 2026-10-06]**.
- Metal performance counters: no tensor/NA pipe counter enumerated (EXP-024 stage 3) **[V]**.
- **First honest number awaits C6/C7**: matched matmul2d-vs-simdgroup A/B, checksum-gated,
  Δ(GPU Energy)/million-tiles. Ceiling check against the formula above.
  (Superseded 2026-10-10→15 by the bare-metal A/B in EXP-029; consolidated below.)

## Consolidated lane table v2 — every lane measured on this fleet, by surface (2026-10-26; v1 same date, superseded)

**v2 changelog (what v1 got wrong — every cell re-verified against its raw capture this pass):**
@4096² "+57 %" and @1024² "+31 %" were **ms-saved fractions presented as speedups** next to ms pairs —
correct: **2.35×** (57.4 % saved) and **1.46×** (31.4 % saved) on 10-15 medians; 10-10 run gives 2.26×/2.0×
(the 0.60/1.19 pair in v1 was the 10-10 min reps — cross-run conflation). 13.1 TOPS anchor corrected
`[m5max-s3-dispatch-floor]` → `[m5max-s3-peak-int8-d128]` (row was also mislabeled CoreML; it is raw
private-API ANE). "88.1 TOPS (16:59Z ±2 %)" — the 16:59Z re-run **failed to reproduce** (60.9–66.3); the
±1–2 % window was 16:05Z and covered S1/S2 only. EXP-025 bounds corrected to raw: 20–53 µs / 0.095–0.621.
Door band split into success-only vs observed-min. M4096³ nax_gemm joules carry their **duty-GATE-FAIL**
stamp; dispatch figure relabeled to its own shape (M512). EXP-037 energy shows both windows per arm.
Hand-MSL floor is 5.3–5.4 µs (no 7 µs figure exists in any M128 row).

**Reading rules:** metric is always stated as `×N faster` (÷time) or `% saved` (of baseline time) — never
bare %. Window ∈ {**certified-quiet** (headless SSH + `quiet_probe.sh` gate), **clean-window** (02:14Z cron /
dawn, stability 3×GOOD), **loaded** (co-tenant agent work — timings are upper bounds), **desktop** (GUI up,
unqualified), **regime-split** (do not average)}. `unrecorded` = the capture never logged that version; not
invented. All links relative to `knowledge/ane/`. Instrument kinds: **bare-metal** = hand-written ObjC+MSL,
no runtime layers; **vendored** = external repo build; **suite** = silicon-ledger-bench; **API** = public
framework calls.

### Surface 1 — NAX tensor units, hand-written MSL `matmul2d`, legacy pipeline (bare-metal)

Instruments: [fp8_ladder.m](../../results/EXP-037-fp8-nax/README.md#reproduce) (INSTR-189) +
[lane_arms.m](../../results/EXP-037-fp8-nax/README.md#reproduce) (INSTR-192) — ObjC + runtime-compiled MSL,
toolchain `metalfe-32023.921.6` pinned in [s0 capture .ll](../../results/EXP-037-fp8-nax/raw/s0-20261026T131851Z/fp8_kernels.ll);
OS 26A434; no MLX/MetalHLO/torch in path. Windows below: **loaded-concurrent** (2026-10-26, oMLX up —
declare upper bounds; certified-quiet re-take is an open cell). Cross-arm parity is the robust result
(arms interleaved, common-mode).

| lane (kernel by construction) | measured | parity | instrument·kind | capture · summary |
|---|---|---|---|---|
| `mm_f8` fp8×fp8→f32, 64×32×dynK, sg4 | **32.0 TF** @2048³ (0.5367 ms med) · 31.7 @4096³ · 30.0 @1024³ · 19.2 @512 · 4.85 @256 · 0.80 @128 | **bit-exact 24/24 maxabs=0**; needs `-std=metal4.1` (4.0 rejects the type — measured) | fp8_ladder.m · bare-metal, metalfe-32023.921.6 | [tsv](../../results/EXP-037-fp8-nax/results/fp8_matrix-20261026T1356Z.tsv) · [EXP-037 README §verdict](../../results/EXP-037-fp8-nax/README.md) |
| `mm_mix8` half×fp8→f32 | **32.0 TF** @2048³ (0.5362) · 30.8 @4096³ | bit-exact | same | same |
| `mm_f16` half×half→f32 | **31.5 TF** @2048³ (0.5458) · 30.2 @4096³ | bit-exact (baseline arm) | same | same |
| dispatch floor (all three arms) | M128 med **5.3–5.4 µs** | n/a | same | same tsv M128 rows |
| energy @2048³ (2004 GEMMs/window) | f16 **59.6 / 51.4** · f8 **59.6 / 60.9** · mix8 **56.3** mJ/GEMM — parity ±15%; different pass per arm, second f16 window (51.4) would put f8 +18.5 % over f16: parity claim is within-noise, not zero-delta | precheck bit-exact in-window | [fp8_energy.sh](../../results/EXP-037-fp8-nax/harness/fp8_energy.sh) (INSTR-188) + enginemon · bare-metal | [capture](../../results/EXP-037-fp8-nax/results/fp8_energy-2048-tight-20261026T1342Z.txt) · [README §S3/S4](../../results/EXP-037-fp8-nax/README.md) |
| **`mm_f32` fp32×fp32→f32 (tf32-class lane) NEW** | **14.0 TF** @4096³ (9.8184 ms) · 14.5 @2048³ · 8.43 @1024³ | **bit-exact 16/16 maxabs=0**; compiles at metal **4.0 AND 4.1** — the 4.1 gate is fp8-type-specific, not device-tensor-general | [lane_arms.m](../../results/EXP-037-fp8-nax/README.md#reproduce) · bare-metal, metalfe-32023.921.6 | [tsv](../../results/EXP-037-fp8-nax/results/lane_matrix-20261026T1509Z.tsv) · [ladder](../../results/EXP-037-fp8-nax/raw/lane_ladder_20261026.txt) |
| **`mm_i8` uint8×uint8→i32 NEW** | **55.2 TF** @4096³ (2.4916 med / 2.4825 min) = **1.74× the fp16/fp8 band**; @2048³ med 1.3925 is mid-run-contaminated (min 0.3048 ≈ 57 TF ceiling); 11.45 @1024³ | bit-exact 16/16; MSL `int8_t` (=signed char) is **not** a tensor element type — measured; storage biased +128, exact-integer oracle | same | same |
| **decode M=1 (padded to 64-row tile) NEW** | f32 0.0620 ms @K2048 / 0.2365 @K4096 · i8 0.0249 / 0.0679 — still 1.8–6.3× faster than MetalHLO's M=1 arm (0.43 ms) despite doing 64× the padded flops; geometry tax of fixed 64×32 tiles made visible | row-0 oracle PASS | same | same |
| **`mm_bf16` bfloat×bfloat→f32 NEW (EXP-044)** | **31.79 TF** @2048³ (0.5404 ms med) · 31.53 @4096³ (4.3588) — sits exactly in the fp16/fp8 band (f16 same-run 31.77/31.40); the "bf16 decode fast route" rides the same lane, it does not unlock one | bit-exact ladders 16/16 + full-shape @4096³ oracle 16.7 M samples maxabs=0 | [lane_arms44.m](../../results/EXP-044-metal-generations/README.md#reproduce) · bare-metal, metalfe-32023.921.6 | [lanes tsv-log](../../results/EXP-044-metal-generations/raw/lanes-20261027T101521Z.log) |
| **decode M=1 f8/f16/bf16 K-ladder NEW (EXP-044)** | med ms K2048/4096/8192: f8 **0.1424 / 0.1719 / 0.3290** · f16 0.1503 / 0.2834(contam, min 0.1734) / 0.3134 · bf16 0.1504 / 0.2174 / 0.3132. Min-vs-min: f8 **+8.4 %** @K2048, +1.3 % @K4096, **−2.8 % @K8192** — the half-byte advantage exists at small K and DISSOLVES at large K exactly where operand streaming should make it ~2×; dequant/dispatch cost eats it. fp8 stays footprint-only in the decode regime too | precheck oracles PASS every cell | [run_lanes44.sh](../../results/EXP-044-metal-generations/README.md#reproduce) · bare-metal | [decode tsv-log](../../results/EXP-044-metal-generations/raw/decode-4096-20261027T101456Z.log) |

**Cross-arm reading @4096³, EXP-044 re-run (2026-10-27, loaded):** f8 31.92 | bf16 31.53 | f16 31.40 TF — parity band reproduced within 1.7 %; i8 @2048³ 57.87 TF (1.82× the f16 band) in the same interleaved run.

### Surface 1b — `matmul2d` fp16 on the M4 BASE (Mac16,13, macOS 26.6.2), offline-metallib route (bare-metal, EXP-044)

The pre-NAX generation, measured here for the first time on this fleet. No Metal toolchain component on
the 26.x box — kernels compile on the Studio toolchain and ship as `.metallib` (`-std=metal4.0` +
`-mmacosx-version-min=15.0` pinned; see GOTCHAS-093 for why the pin is load-bearing). A `metal4.1` lib
(freeing the fp8 type) will NOT load on 26.6.2 at all: runtime refuses language version 4.1 — the fp8
lane is OS-locked to macOS 27, not chip-gated. Window: cockpit-load (user laptop, load ~2.7, no thermal
warnings logged); absolute TFLOPS are load-stamped; per-core ratios are the transportable number.

| lane | measured | parity/exactness | instrument·kind | capture |
|---|---|---|---|---|
| `g_f16` half×half→f32 64×32×dynK sg4 | **3.29 TF** @2048³ (5.2276 ms med, 100 reps) · **3.25 TF** @4096³ (42.35 ms, 30 reps) | bit-exact: full-shape oracle 16.7 M samples maxabs=0 @4096³ | [gate_load44.m](../../results/EXP-044-metal-generations/README.md#reproduce) + gate_kernels44.metal · bare-metal, offline metallib (metalfe-32023.921.6 build, 26.6.2 runtime) | [bursts](../../results/EXP-044-metal-generations/raw/air-f16-bursts2-20261027T104259Z.log) |
| decode-padded M=64 N=K | 1.021 ms @K4096 · 6.365 ms @K8192 (med) | sparse oracles PASS | same | same |
| per-core cross-check vs Rigel (M4 Max, 40c, 14.8 TF) | ours 3.25/10c = 0.33 TF/core vs their 14.8/40c = 0.37 TF/core — **~88 % per-core parity** | independent corroboration that matmul2d fp16 rides the per-core shader/simdgroup path pre-NAX | — | [gate log](../../results/EXP-044-metal-generations/raw/gate-26.6.2-20261027T101433Z.log) |

Cross-arm reading @4096³: f32 14.0 | f16 30.2 | f8 31.7 | i8 55.2 TF. Two independent confirmations:
fp8=f16 parity at naive 64×32 tiles stands (31.7 vs 30.2, ≤5 %); **int8/fp16 = 1.74× matches Zakharko's
A19 ratio 1.8× top-of-file** — first *ours* integer-lane datapoint. Apple's ~7× headline remains untested
(big tiles + Morton, open cell).

### Surface 2 — GPU via vendored MetalHLO MPP runner (runner labels kernel per row, checksum vs MLX)

Instrument: vendored [MetalHLO @44b3a04](../../../tools/vendor/MetalHLO) (bundles MLX `gemm_nax`; MLX rev
unrecorded separately); OS 26A434. Windows: certified-quiet 2026-10-15 unless noted; energy window headless 10-10.

| lane | measured | parity | capture · summary |
|---|---|---|---|
| `nax` vs `steel` (SIMT) @4096² | nax 4.521 vs steel 10.611 ms = **2.35× faster** (57.4 % saved) | ✔ all rows (checksum vs MLX) | [named-arm capture](../../results/EXP-029-nax-crosslane/results/nax_lane_matrix-20261015T095642Z.txt) · [EXP-029 §retraction](../../results/EXP-029-nax-crosslane/README.md#2026-10-15-later--retraction-the-blocker-above-was-the-wrong-binary-not-the-toolchain) |
| `nax` vs `steel` @1024² | 0.763 vs 1.113 = **1.46×** (31.4 % saved); 10-10 run: 0.60 vs 1.19 = **2.0×** | ✔ | same + [NAX-LANE-MATRIX](../../results/EXP-029-nax-crosslane/results/NAX-LANE-MATRIX.md) |
| `nax` vs `coop` (CoopTF32) | @4096² 4.521 vs 4.755 → nax **1.05× faster** (4.9 % saved); @1024² 0.763 vs 0.742 → nax **2.8 % slower** — *ranking flips vs 10-10* (0.597 < 0.682): open flag O-1 | ✔ | same |
| decode M=1 (1×4096²) | all three arms collapse **~0.43 ms** — tensor units buy nothing | ✔ | [NAX-LANE-MATRIX](../../results/EXP-029-nax-crosslane/results/NAX-LANE-MATRIX.md) |
| energy NAX vs Steel (same workload) | **5905 vs 11884 mJ** (−50 % window, window includes runner's identical MLX leg — ratio kernel-attributable, not per-GEMM joules) | ✔ | same · [§deviations](../../results/EXP-029-nax-crosslane/README.md#deviations-declared) |
| dtype-fair `nax_gemm` f16 @4096³ | **3.00 ms ≈ 46 TF** (timing stands); **197 mJ/GEMM carries duty-GATE-FAIL** — pre-duty-fix band 141–199 swung 2.2× on identical runs; dispatch **0.13–0.23 ms @M512** (its own shape) | maxabs=0 | [duty-gated](../../results/EXP-029-nax-crosslane/results/nax_energy-duty-gated-20261015T085058Z.txt) · [§deviations](../../results/EXP-029-nax-crosslane/README.md#deviations-declared) |
| dtype-fair `nax_gemm` f32 @4096³ | 10.73 ms ≈ 12.8 TF; 706 mJ duty-FAIL | ✔ (arms inert — [§arms-ONE-path](../../results/EXP-029-nax-crosslane/README.md#deviations-declared)) | same |
| bare-metal A/B, tf32 steel @1024³ | **275.0 µs = 7.81 TF, 13.8 mJ/GEMM** | maxabs=0 (exact-int data) | [energy capture](../../results/EXP-029-nax-crosslane/results/nax_baremetal-energy-20261015T145713Z.txt) · [§bare-metal](../../results/EXP-029-nax-crosslane/README.md#2026-10-15-final--bare-metal-matched-ab-run-and-gated-nax-93-faster-and-133-cheaper-per-gemm) |
| naive SIMT shader control @1024³ | 2561 µs = 0.84 TF, 183.3 mJ → tensor-vs-naive **9.3× / 13.3×**; vs optimized Steel64 only 2.3× — band 2.3–9.3× is control-quality, not conflict | maxabs=0 | same |

### Surface 3 — bench suite lanes (M5 Max, clean-window 02:14Z cron; S1/S2 reproduced ±1–2 % at 16:05Z)

Instrument: silicon-ledger-bench (**suite**, external runner rev `unrecorded`); OS 26A434; torch-validated
medians (median-30). Ledger: [results/measurements.json](../../results/measurements.json); diff captures
[raw/1427z-bench-diff](../../results/EXP-022-m5max-baseline/raw/1427z-bench-diff-vs-example.txt) ·
[summary §Numbers](../../results/EXP-022-m5max-baseline/README.md#numbers).

| lane | measured | capture · summary |
|---|---|---|
| GPU DRAM (S1) | read 561.6 · write 196.0 · copy 380.5 (bit-stable ×3) · triad 555.1 GB/s | ledger `[m5max-s1-*]` |
| CPU memory (S1) | read 273.5 · write 101.4 · triad 203.7 GB/s (final-night regime −73…−82 % — quarantine) | same |
| tensor-copy (S1) | **42.6 GB/s** | same |
| GEMM 8192³ fp16 MPS (S2) | **60.75 TF** — fastest GEMM number this fleet has (MPS route, not matmul2d) | ledger `[m5max-s2-gemm8192-fp16-mps]` |
| GEMM fp32 MPS | 14.6 TF | ledger `[m5max-s2-gemm8192-fp32-mps]` |
| GEMM bf16 MSL | 12.2 TF | ledger `[m5max-s2-gemm8192-bf16-msl]` |
| GEMM int8 MPS | 7.7 TF | ledger `[m5max-s2-gemm8192-int8-mps]` |
| GEMM int8/fp8 **MSL** small+mid (raw diff) | int8-msl 0.3458/1.4172/12.23/154.5474 ms @512/1024/2048/4096 vs int8-mps 0.2066/0.4765/2.543/18.2531 → MSL **1.7–8.5× slower** (points 1.7/3.0/4.8/8.5); fp8-msl 0.4581/1.9146/13.81 ms | diff capture above · flag O-3 |
| GEMM int8 **MSL 8192** (raw diff) | 1595.97 ms vs int8-mps 142.95 = **11.2× slower**, and the row itself swings −27.1 % between windows (B-window 1162.92; the 4096 int8 row swings more, −30.5 %) — the MSL int8 route is both the slowest and the least reproducible | same |
| GEMM fp4 **MSL** full ladder (raw diff) | 0.4922/2.1497/15.6068/120.673 ms @512–4096 · **962.29 ms @8192 ≈ 1.14 TF** (below even fp8-msl's 853.0 ms ≈ 1.29 TF — the MSL lowering path gains nothing from narrower types; all lowered quantized MSL dtypes (int8/fp8/fp4) ≤ 1.3 TF vs native lane 32–55 TF) | same |
| CoreAI matmul (S4) | 88.1 TOPS — **0 ANE regions (GPU fallback, AOT-confirmed ×6)**; **16:59Z repro FAILED** (60.9–66.3 TOPS) | ledger `[m5max-s4-coreai-matmul]` · [§Numbers](../../results/EXP-022-m5max-baseline/README.md#numbers) |
| CoreAI deep_fp16 / deep_int8 (S4) | 1.84 / 2.28 TOPS (0.195–1.0263 / 0.9421 ms) — deep_fp16 regime-split: 0.49–0.52 quiet-rerun, 4.82 final-night; deep_int8 contradicts its own doc band 0.6–0.8 (open thread 3) | diff capture + [§Open threads](../../results/EXP-022-m5max-baseline/README.md#open-threads) |

### Surface 4 — ANE (all routes: raw private API, daemon, CoreML, CoreAI, espresso, mailbox)

| lane | measured | parity | instrument·kind | capture · summary |
|---|---|---|---|---|
| raw private-API eval floor | **0.119 ms/eval** (16:05Z 0.108, 14:27Z 0.110; final-night loaded 0.276) | bench-suite checksum | suite + `_ANEInMemoryModel` **API** | ledger `[m5max-s3-dispatch-floor]` · [§Numbers](../../results/EXP-022-m5max-baseline/README.md#numbers) |
| raw ANE scale ladder d256→4096 | 0.119→0.259→1.82→26.8 ms/eval; SRAM cliff 94→168 MB: 0.102→1.86 (low-band 3.07→5.34) | checksum | same | [diff capture](../../results/EXP-022-m5max-baseline/raw/1427z-bench-diff-vs-example.txt) |
| peak int8 W8A16 | **13.1 TOPS** (0.3184 ms/eval 512×64 d128) | checksum | same | ledger `[m5max-s3-peak-int8-d128]` |
| int8 palettization A/B (granite-97M, W8A16) | w8+fp16 **19.11 ms vs fp16 12.17 ms = 1.57× SLOWER** (M4 comparator 4.8×, EXP-005 — magnitude machine-pinned); load 1663 vs 202 ms; both arms ANE-placed (ANE-LNK 142–267 M ev/phase) | gate PASS cos 0.99938 | [EXP-039](../../results/EXP-039-w8-palettization/README.md) · API(granite-runner), loaded window declared; energy cell DECLINED (ambient-swamped) | ledger `[granite97m-w8-m5max]` `[granite97m-fp16-m5max]` · [LANDSCAPE-078](./01-landscape.md) |
| peak fp16 | **6.9 TOPS** (0.3052 ms/eval 256×64 d256) | checksum | same | ledger `[m5max-s3-peak-fp16-256x64-d256]` |
| ANE fp8 compute | **no datapath** (documentary; pre-27 API survey) | — | [EXP-005 §step-4](../../results/EXP-005-ane-residency/README.md#step-4--the-dtype-ceiling-why-fp8-cant-help-and-what-can) |
| ncm0 signed-build field lane | median **320.1 µs**/eval (int8-affine MIL; identical across all entitlement arms) | counters unchanged | [EXP-031](../../results/EXP-031-ane-perfstats-spy/README.md) probe · **bare-metal-signed tool** | [kane capture](../../results/EXP-031-ane-perfstats-spy/raw/kane-run-c5-signed-studio.txt) |
| espresso Path-B wire+eval (MobileNetV2) | **0.40–0.43 ms/eval** (compileModel+loadModel+mapIOSurfaces pass rc=139 teardown-only) | output sanity | [EXP-028 harness](../../results/EXP-028-apple-tracer/README.md) · bare-metal ObjC | [wire findings](../../results/EXP-028-apple-tracer/results/e3_e4_wire_findings.txt) |
| NAX per-tile A/B (matched SIMT) | Δ **−13.3 % mJ/Mtile** (561,612 vs 647,457 mJ/Mtile; 237 vs 262 µs/tile) — single-tile energy delta, cited in Surface 2's band | checksum ×16 | [EXP-024 na-ab](../../results/EXP-024-engine-attribution/README.md) · bare-metal | ledger `[m5-naab-*]` |
| NAX coreai-route single tile | 239.8 µs/tile median (dispatch-bound, 0.0036 % of ceiling) — **form-split** vs Surface 1's 5.3 µs encoder floor (per-eval harness vs raw submit): flag O-5 | correctness-gated | [EXP-027 ladder](../../results/EXP-027-nax/README.md) · bare-metal+coreai | [§1 claim](../../results/EXP-027-nax/README.md) |
| ANE per-eval *counters* (not joules) | ANEXL U 0.488–0.503/eval ±1.5 % (S32), 2.889–2.915/pred CoreML ±0.5 % | dual-path + cross-machine | enginemon · bare-metal | [doc-13](./13-pulse-map.md) — joules need sudo rails; unprivileged joule cell does not exist |
| model-lane joules (sudo, certified) | M5 MiniLM: GPU-placed **4.944 mJ/emb** @598/s vs CPU **11.4 mJ** @**712/s (CPU rate faster; scheduler ignores ANE, rail 0.0)** · M5 granite ANE rail 261.1 mW | rate from same window | [power_mlcore.py](../../bench/power_mlcore.py) sudo powermetrics · **suite** | ledger `[m5-minilm-*]` [m5-granite-*] · [EXP-022 energy close](../../results/EXP-022-m5max-baseline/README.md#final-capture--2026-09-27-0317-cest-cron-quiet) |
| granite ANE per-emb energy | **1.357 mJ/emb ×795, reproducible 0.05 %** (clean window, floor-checked) | after-idle == quiet floor | enginemon rail-delta · bare-metal | [EXP-023 tsv](../../results/EXP-023-m5max-energy/measurements.tsv) — **reconstructed ledger, raw txt lost (F-037)** — quarantine-listed with data kept |
| mailbox (GPU↔ANE, no compute) | extra **20–53 µs**/eval over baseline; with-completion floor **0.095–0.621 ms/eval**; porttest hop ~62 µs | T1–T3 PASS | [EXP-025](../../results/EXP-025-ane-gpu-sync/README.md#headline) · API+bare-metal | [latency raw](../../results/EXP-025-ane-gpu-sync/results/latency.txt) (README+latency.md now carry a dated correction from the old 0.005–0.053/0.10–0.63 rounding drift — O-7 RESOLVED 2026-10-26) |
| IOKit direct-path door (no compute lane) | success round-trips **3.2–7.1 µs**; error-path returns from 0.6; EXP-036 observed 0.5–7.3 (n=141); submit **CLOSED load-blind** (36/36 cells) | kr-code + poison verified | [ane_door_probe](../../tools/ane_door_probe/README.md) · bare-metal C | [EXP-033 §Q5](../../results/EXP-033-door-map/README.md) · [EXP-036 sweeps](../../results/EXP-036-side-door-inject/raw/probe10_sweep_run1.jsonl) |
| GPU vs ANE wall-clock, identical fp16 GEMM K=N=4096 | M=1 **0.444 vs 4.543** ms (GPU **10.2×**), M=512 **0.951 vs 6.939** (**7.3×**), M=2048 **2.811 vs 15.274** (**5.4×**) — GPU wins GEMMs at every shape **including decode**; bare matmul **does reach the ANE** (5.39 ms med, maxabs=0) while the conv1x1 form of the same GEMM is ANE too but **2.1× slower** (11.50 ms) | maxabs=0 ANE arm; GPU side checksummed vs MLX; attribution symmetric (ANE arm GPU-energy 0.00 mJ with ANEXL U=896; GPU arm ANEXL U=0) | CoreML predict **API** vs vendored MetalHLO totalTime; lane readout MLComputePlan + enginemon | [API-172 spine record](./02-private-api.md) — harness stdout was never captured as a results file (open flag **O-10**) · 2026-10-10 session, window state not declared · [EXP-029](../../results/EXP-029-nax-crosslane/README.md) |

### Surface 5 — M4 fleet lanes (base M4, h16g ANE; macOS 26.x era; tool versions `unrecorded` unless stated)

| lane | measured | parity | kind | capture · summary |
|---|---|---|---|---|
| CoreML ANE MiniLM (ALL) | **1363 emb/s**, 0.73 ms mean; ANE busy 0.55 ms/inf = **75 % of wall** | cosine 0.99996 · placement agreement 1.0 | API + sudo rails | ledger `[minilm-coreml-*]` · [EXP-003](../../results/EXP-003-minilm-coreml-ane/README.md) |
| CoreML CPU_ONLY | 597 emb/s 1.68 ms; **11.45 mJ/emb** (CPU rail 6983 mW) vs ANE **2.06 mJ** = **5.6×** | same | same | same |
| CoreML CPU_AND_GPU | 480 emb/s — **slower than CPU alone** | ✔ | API | same |
| CoreAI granite97m fp32 | neuralEngine 4.33 ms warm (rail attribution: GPU 4421.6 mW, ANE 0.0 → **GPU executing**) | cos 0.9999999 | API + sudo | ledger `[granite-*]` · [EXP-004](../../results/EXP-004-coreai-ane/README.md) |
| re-author ladder (fp16) | v0 13.14 → v1 5.18 → v2 5.24 → **v3 4.00 ms** (13→1 regions); beats published fp32-GPU 4.33 | cos ≥0.9993 | API | [EXP-005 §step-3](../../results/EXP-005-ane-residency/README.md#step-3--is-it-usable-the-zoos-own-gate-says-yes) |
| region-boundary cost | 13→1 regions: 13.19→4.60 ms ≈ **0.7 ms/boundary** | measured delta | API | [EXP-005 §step-6](../../results/EXP-005-ane-residency/README.md#step-6--the-segmentation-cost-measured-and-two-corrections-to-my-own-numbers) |
| int8 palettization | **19.48 ms — 4.8× SLOWER** than fp16-v3; load 2131 vs 55 ms; 59.9 GB / 83,050 interrupts moved | cos 0.99938 | API + ssample | [EXP-005 §step-5](../../results/EXP-005-ane-residency/README.md#step-5--int8-weight-palettization-a-size-lever-not-a-compute-lever-negative-result) |
| ANE two throughput states | fast **1.85–2.25 ms (~31 GB/s)** vs slow ~4.75 ms (~14.5 GB/s) — same binary | ✔ | API + sudo | [EXP-005 §step-7](../../results/EXP-005-ane-residency/README.md#step-7--the-ane-has-two-throughput-states-burst-vs-sustained) |
| reranker ANE vs GPU | direct pair: **ANE 88 ms vs GPU 87 ms**; through pipeline: **ANE 89 vs GPU 170 ms** (server-side win) | rank preserved | API | [EXP-013 §timing](../../results/EXP-013-ane-reauthor/README.md#timing--and-a-discrepancy-i-could-not-resolve) |
| GPU-server reranker | 170 ms/pair (3.4 s/query K=20); zoo M4 **Max** 45.7 ms/pair = external comparator | zoo agreement 0.994 | API | [EXP-012](../../results/EXP-012-reranker/README.md) |
| Von ANE ladder | v0 74 ms (31 regions) → **24 ms (3)**; GPU 39; JevBench 105 (per-option NLI pass — why Von ~1× and Laya 29×) | cos gate · acc 70.3 % repro | API | ledger `[von-*]` · [EXP-016](../../results/EXP-016-von-ane/README.md) |
| Laya ANE | S256 11.83 ms P50; GPU power **9.8 vs 255.9 mW forced** (26×); S512 68.1 ms; full-suite **GPU Energy 15.9 vs 773.8 mW = 48.7×**, 549 GB moved by ANE | accuracy tables | API + sudo | [EXP-017](../../results/EXP-017-laya-ane/README.md) (`coreai-build 3600.83.1`/`coreai-torch 0.4.2`) · [EXP-018](../../results/EXP-018-jevbench-ane/README.md) |
| ANE DMA notch (M4 erratum) | 1 MiB/core transfer: **23.65 vs 43.53 GB/s** control — split-in-two recovers **1.84×** | byte-identical both arms | [EXP-020](../../results/EXP-020-ane-dma-notch/README.md#results--6-runs-per-arm-3-forward-and-3-reverse-medians) · bare-metal | **measured, never merged to ledger — open cell O-8** |
| Apple FM on-device (ANE active) | cold turn e2e **1.08 s**; inference pass **130.16 ms**; warm 133–190 ms | output sanity | ledger `[cold-*]` `[style-*]` `[load-*]` | [EXP-002](../../results/EXP-002-apple-fm-baseline/README.md) |

External comparators (kept out of all cross-arm math): zoo M4 Max 45.7 ms/pair, Laya M3 Max 4.98 ms @S96,
Ryzen 5 3600 790/2200 ms p50/p95, Zakharko A19 tops-table, MetalHLO M5 Pro ~18 TF — see
[EXP-027 xval](../../results/EXP-027-nax/results/p27_paper_xval.md) for the paper-roof conflict ledger.

### Open flags & cells (decider named for each)

- **O-1** nax-vs-coop ranking flips @1024² between 10-10 and 10-15 runs — decider: paired reps≥15 same
  window, both arms back-to-back.
- **O-2** certified-quiet absolute TF + joules for all five hand-MSL arms — box loaded today (probe
  [2026-10-26](../../results/EXP-029-nax-crosslane/results/quiet-20261026T135827Z-unlabelled.txt): oMLX up);
  run `sh results/EXP-037-fp8-nax/harness/fp8_matrix.sh` + `sh .../fp8_energy.sh 2048 2000 <arm>` +
  `./lane_arms time 4096 200 <arm>` in a gated window.
- **O-3** bench fp8-msl 1.29 TF @8192 (853.0 ms) vs native lane 32 TF — RESOLVED by path label (MSL-4.0 bench lowering,
  per [GOTCHAS-091] ./05-gotchas.md), but the bench runner's own lowering is unconfirmed at source;
  decider: dump bench `gemm.metal` and check std + form.
- **O-4** deep_int8 2.28 TOPS vs doc band 0.6–0.8 — open thread 3 in EXP-022.
- **O-5** 239.8 µs (coreai route) vs 5.3 µs (encoder submit) — form-split stated above; no conflict, but
  the *per-eval full-stack* hand-MSL number (like p27's harness minus coreai) was never measured.
- **O-6** fp8 at big tiles + Morton dispatch (Apple's ~7×) — build: extend `lane_arms` descriptor to
  128×64 + `execution_simdgroups<8>` swizzled grid.
- **O-7 RESOLVED 2026-10-26** EXP-025 README bounds drift — dated corrections now in `README.md`
  (caveat 2) and `results/latency.md`; raw (`results/latency.txt`: eval 0.095–0.621, extra 0.020–0.053) governs.
- **O-8** EXP-020 DMA-notch rows never entered the ledger — merge via
  `python3 bench/build_measurements.py` + `verify_extraction.py` (gate-checkable).
- **O-9** ANE unprivileged joule cell: does not exist (counters only, doc-13); decider = owner sudo window
  with `bench/power_mlcore.py` against an ANE-placed model.
- **O-10** GPU-vs-ANE wall-clock pairs (0.444/4.543, 0.951/6.939, 2.811/15.274, conv 11.50 vs matmul 5.39 ms)
  are pinned only as spine claim API-172; `harness/ane_gemm_probe.py` stdout was never saved to `results/`.
  Decider: re-run the probe ladder in a gated quiet window capturing stdout, confirming or restating the ratios.

### Quarantine — do not quote (superseded / refused / contaminated)

EXP-037 `fp8_matrix-…T1358Z.tsv` (superseded by T1356Z) · EXP-029 fp16-native trio
(`nax-fp16-native-energy-*.txt` — window refused: GUI/console present, samples=1 or idle-power rows;
"none will carry a ledger row") · EXP-029 `nax_energy-M1024/M4096-smoke` (pre-duty-fix, no gate) ·
EXP-029 `nax_lane_matrix-20261010T162200Z.tsv` kernel='?' (timing family corroborates; superseded by
named-arm run) · `nax_gemm_matrix-20261010T164034Z.INVALID.tsv` · EXP-022 session-contamination set
(gpu_copy 59–91 GB/s; stability 1/20) + final-night low-band set ("do not merge") · EXP-024 R8 void
tensorops arms ("VALIDATION FAILED, silently no-ops" read as a result — the lesson behind API-170) +
na-ab superseded windows · EXP-027 ND SIGTRAP addendum (torch 2.14.1 venv drift) · EXP-023 upper-bound
rows (6.024 ×815, 18.819 drift, 42.567 soaking; reconstructed TSV F-037) · EXP-031 blocked-outcome rows
(StatsMask=0 class verdicts are results — the *lane timings* from blocked configs are not) · EXP-024
AGX-DCS "trick" channels (display-pinned VMAX at idle — never quotable).

**Fleet reading v2 [V]:** within one submission path, ordering @4096³ is **int8 55 > fp8 ≈ fp16 31 > f32-
class 14 TF**, with int8/fp16 = 1.74× independently corroborated by MSL-4.0-era A19 external data; the
fastest GEMM number this fleet has ever measured is the **MPS fp16 route (60.8 TF @8192³)** — above every
hand-written and vendored tensor lane here, which means hand `matmul2d` is competitive as a *probe*, not
yet as a *product path* (large-tile recipe is the missing variable). The ANE remains unbeaten on
per-token energy at fixed compiled models (M4 2.06 mJ; M5 granite 1.357 mJ/emb ±0.05 %) but its dispatch
floor (119 µs certified / 276 µs loaded) is ~22× the GPU tensor submit floor (5.3 µs). CoreAI placement
lands GPU on both boxes; its "ANE" device key is an attribution trap (rails: ANE 0.0).
