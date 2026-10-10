# NAX lane matrix, measured (2026-10-10, headless SSH-only box, MetalHLO runner)

Source TSV: `results/nax_lane_matrix-20261010T162200Z.tsv`. Runner: vendored MetalHLO
`mlx-comparison --quick --filter <shape>` (3 warmup + 10 measurements per run), correctness
validated by the runner against MLX (every row printed OK). Arms (all INSIDE the GPU, API-164):

| arm | kernel | switch |
|---|---|---|
| nax | MPP `gemm_loop` (MLX-grade cooperative tensor) | `METALHLO_NAX_GEMM=1` |
| coop | MPP cooperative-tensor tf32 (default) | (none) |
| steel | hand-rolled `simdgroup_matrix` shader/SIMT | `METALHLO_COOP_GEMM=0 METALHLO_FORCE_STEEL=1` |

## Timings (ms, 2 reps — spread was ~1-3%)

| shape | nax | coop | steel | MLX | nax vs steel |
|---|---:|---:|---:|---:|---:|
| MAT-DOT-003 1024^2 | 0.60 / 0.62 | 0.68 / 0.69 | 1.19 / 1.21 | ~0.50 | **2.0x** |
| MAT-DOT-004 2048^2 | 1.32 / 1.36 | 1.74 / 1.74 | 1.59 / 2.09 | ~1.25 | 1.2-1.5x |
| MAT-DOT-005 4096^2 | 4.78 / 4.80 | 5.67 / 5.68 | 10.79 / 10.92 | ~3.8 | **2.26x** |
| MAT-DOT-008 decode (1x4096 @ 4096x4096) | 0.43 / 0.44 | 0.42 / 0.43 | 0.43 / 0.43 | 0.74-1.30 | 1.0x |

**Reading**: NAX is the fastest GPU datapath for compute-bound shapes (1024^2 2.0x, 4096^2 2.26x vs
the SIMT/Steel path), and at the **decode shape (M=1) all three collapse to ~0.43 ms** — the tensor
units buy nothing there (consistent with the prefill-vs-decode envelope). MetalHLO beat MLX on that
decode shape (0.43 vs 0.74-1.30 ms).

## GPU energy per arm (enginemon wraps the same runner; same total workload)

| arm | GPU energy | window | mean power |
|---|---:|---:|---:|
| NAX | **5905 mJ** | 2.2 s | 2666 mW |
| Steel | **11884 mJ** | 2.6 s | 4642 mW |

**~2.0x less energy for ~2.1x less time** — the energy win tracks the time win; NAX does not pay a
power penalty to be faster (this supersedes the single-tile EXP-027 delta of -13.3% mJ/Mtile with the
real-shape picture).

## Caveats

- The energy window includes the runner's own MLX leg (identical for both arms), so the 2x ratio is
  kernel-attributable but is **not** an absolute per-GEMM joule number; a MetalHLO-only harness is the
  clean follow-up.
- These are MetalHLO's own harness timings, not yet our gated protocol (idle-band + checksum + IQR).
- fp32 inputs: the coop/NAX arms run tf32 (relaxed precision); the steel arm is exact fp32 — so the
  arms differ in precision, not only in datapath. fp16 arms are the next cell to fill.
