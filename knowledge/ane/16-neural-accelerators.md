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
