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
- Works on Xcode 26.1/26.x stable **[C]** — our R8 matmul2d multi-tile no-op is therefore
  a 27.0-beta GPUCompiler (metalfe-32023) regression, not an OS-level impossibility.

## Ceiling arithmetic for C8 re-audit **[C-formula]**

NA fp16 ceiling = N_matrix_cores × 1024 × clock. Two readings of N:
- **GPU-core count (Zakharko, marketing)**: M5 Max 40 cores @ ~1750 MHz → ~70 TFLOPS
  fp16, ~130 TOPS int8.
- **HAL compiler-suffix count (2606.22283 mapping, h17c = 32)**: 32 × 1024 × 1.4–1.8 GHz
  → 46–59 TFLOPS.
Difference is exactly the layer question (all matrix-capable GPU cores vs compiler-visible
sets). Use the HAL 32-core number as the conservative denominator for efficiency ratios;
quote the marketing 70 TFLOPS only next to its provenance. C8 audit annotates both.

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
