# EXP-029 — NAX cross-lane: when to use the tensor units, and when not to

Machine: Mac17,14 (M5 Max, h17c), macOS 27.0.1 (26A434).
Question (owner, 2026-10-10): NAX are documented and GPU-bound — **how do they work, what are their
limits, and when should a workload use them over the ANE or plain GPU?** Same discipline as the ANE
work: every claim sourced, every number reproducible, nothing asserted that was not run here.

Status: **scaffold** — protocol + claims inventory written; the bench arms are gated on a **user
quiet window** (oMLX is live on this box and the standing rule forbids agent GPU *energy* work
while it runs).

## 1. What is already established (do not re-derive)

| fact | evidence |
|---|---|
| NAX exist as a real second datapath, submission is **not** a dedicated call: MTLBuffer bytes + a `matmul2d` instruction claim them; single-tile eval median **239.8 µs** | `results/EXP-027-nax/results/p27_r8_ladder.txt`, `NAX-SUBMIT.md` |
| Per-tile cost vs matched SIMT arm: **561,612 vs 647,457 mJ/Mtile (−13.3%)**, signal 1210× the idle floor; dispatch-bound at single-tile size | `results/p27_counters.txt` + EXP-024 C7 |
| Multi-tile via the coreai compiler route: **R8 NO-GO** (exactly one tilegroup completes); system GPUCompiler rejects MSL 4.0/4.1 (CLT has no matmul2d headers) | `results/p27_r8_ladder.txt` |
| Public multi-tile recipe exists and builds with Xcode-27: MetalHLO @44b3a04 bundling MLX `gemm_nax` (vendored `tools/vendor/MetalHLO`) | `results/p27_metalhlo_build.txt` |
| Observability: **zero** TENSOR/NAX-named IOReport channels; `PS13` is generic top-perf-state engagement, NOT matmul2d-exclusive; the ANE lenses (`ANEXL U`, `ANE UP`) are ANE-exclusive and calibrated | `results/p27_nxd_nax_lenses.txt`, `p27_anpos_promote.txt` |
| Ceiling arithmetic: NA fp16 ≈ N_cores × 1024 FLOPS/core/cycle; `h17c = 32` triple-sourced → 46–59 TFLOPS conservative; marketing 70 TFLOPS | `knowledge/ane/16-neural-accelerators.md` |
| Known silent-zero traps (our bug, their repro): MTL4Compiler pipeline path, innermost-first extents, residency set, threadgroup-memory length | `knowledge/ane/10-m5-attribution-signals.md` Q5 |

## 2. Documented limits (primary + working-compiler sources; NOT yet tested here)

From Apple's pinned primaries (`raw/research-2026-10-08/mpp_programming_guide.pdf`,
`wwdc2026_330_metal_tensors.html`) and from MetalHLO's shipped gating code
(`metalhlo_codegenerator_nax_gating.txt`, `metalhlo_codegenerator_mpp_matmul_template.txt`):

| constraint | value / rule | source |
|---|---|---|
| API requirement | MPP `matmul2d` needs **Metal language 4.0** and **Apple9 family (M3+)** | MetalHLO gate |
| shape alignment | MPP path gated on `M%8==K%8==N%8==0 && M,K,N ≥ 8`; Steel fp32 path needs `M%64==N%64==0, K%16==0` | MetalHLO gate |
| tiles | 128×128 with **8 simdgroups / 256 threads**; 64×64 with 4 simdgroups / 128 threads for low occupancy | MetalHLO template |
| occupancy gates | use128 needs `(M/128)(N/128)·batch ≥ 128`; use64 needs `tg64 ≥ 16` | MetalHLO gate |
| extent order | `dextents`/`slice` are **(cols, rows)** — inner-stride dim FIRST | MetalHLO template; matches our own Q5 finding |
| host API | plain **MTLBuffers are enough** — no MTLTensor host API required | MetalHLO template |
| dtype | matrix coprocessor tuned for half/bfloat; fp32 runs via **tf32 relaxed_precision** | MetalHLO template |
| NAX cooperative config | BM=64, BN=128, BK=256, WM=2, WN=4 (SM=SN=32, 8 simdgroups); **UM/UN/UK = 16/32/16, SK=32** are the coprocessor's natural units | MetalHLO `naxGemmConfig` |
| occupancy knob | `max_total_threads_per_threadgroup` must match the simdgroup count or the register-heavy kernels lose occupancy | MetalHLO NAX source |
| L2 reuse | `swizzle_log = 2` on Pro devices reshapes the grid so resident threadgroups share tiles | MetalHLO NAX source |
| fp32 guidance is stale | MLX avoids MPP for fp32 (older silicon); on Apple9 MetalHLO **measured** MPP fp32 ~5–10× faster than a hand-rolled simdgroup fp32 kernel, and tf32 takes fp32 matmul from **~3.6 TF (exact) toward ~18 TF** on M5 Pro | MetalHLO comments (their measurement, not ours) |
| crossover | matmul2d beats `simdgroup_matrix` only at **M ≳ 400** (18.9 vs 11.8 TF at M=1024) on the same chip; decode (M=1) stays on the shader path | Tungsten article (SOURCES.md) |

## 3. The bench (this is the missing piece)

Matched-shape, correctness-gated cross-lane matrix. **Every arm runs the same shapes and is
validated by checksum before any timing is believed** (the R8 and Q5 episodes both produced
"fast" numbers from kernels that wrote nothing).

Arms (lanes):
1. **NAX/MPP fp16** — `matmul2d<desc, execution_simdgroups<8>>`, 128-tile (and 64-tile variant).
2. **NAX/MPP tf32** — same shape, `relaxed_precision=true`, fp32 in/out.
3. **GPU SIMT fp16/fp32** — MSL `simdgroup_matrix` (the incumbent).
4. **ANE fp16** — the same GEMM as a Core ML / MIL matmul (our existing ANE arms).
5. **CPU** — Accelerate/BNNS reference (correctness anchor, not a perf target).

Shapes: decode-shaped (M=1, K=4096, N=4096) / prefill-shaped (M∈{128,256,512,1024,2048},
K=N=4096) / batched (batch∈{1,8}) — chosen so the gating rules in §2 land on both sides
(M%128, tile-count ≥128, the M≈400 crossover).

Metrics per arm: (a) wall time per tile and total; (b) **GPU Energy (powermetrics rail)** and ANE
rail where applicable; (c) Δ energy vs the SIMT arm; (d) max-abs error vs the CPU reference;
(e) `PS13` engagement (as a *generic GPU* signal only — never as a NAX counter).

Gates: checksum/`max_abs_err ≤ tol` or the row is discarded; identical buffers and dispatch
geometry across arms; one shape per process; N repeats ≥ 20 with median+IQR; **quiet window
required** (no oMLX, no display-pinned load elsewhere).

## 4. Harness plan

- `harness/nax_bench.m` — single binary, `--lane nax-fp16|nax-tf32|simt|ane|cpu --M --N --K --batch`,
  writes TSV rows (`lane shape median_us iqr mJ max_abs_err`), refuses to emit a timing row whose
  checksum failed.
- `harness/run_matrix.sh` — drives the TSV; refuses to start when oMLX is present unless
  `NAX_ALLOW_LOADED=1`.
- energy sampling: `powermetrics --samplers gpu_power` (GPU rail + the ANE rail for the ANE arm),
  one sample stream per arm, aligned to the timed loop.
- correctness anchor: `harness/accel_ref.c` (Accelerate) producing the golden matrix once per shape.

## 5. Deliverable

A decision table — *for shape S, use lane L* — with the NAX eligibility predicates from §2 as the
first column, backed by measured numbers rather than vendor TFLOPS. Records: API (limits/measured
envelope) + GOTCHAS (the practical "can I use NAX here?" gate).

## Deviations (declared)

- Bench not yet run: oMLX live → agent GPU energy work forbidden by standing rule. Correctness and
  latency arms may be built and smoke-tested first; **energy arms wait for the owner's quiet window**.
- §2 constraints are documented (Apple primaries + MetalHLO's shipped code), not yet reproduced on
  this box; each becomes a tested claim only when EXP-029 runs it.
- MetalHLO's fp32/tf32 numbers are *their* measurement on M5 Pro — cited as external, to be
  re-measured here.
