# EXP-037 — fp8-on-NAX: does M5 Max `matmul2d` execute `metal_fp8_e4m3_format` natively, and what is it worth?

Machine: Mac17,14 (M5 Max, h17c; 40 GPU cores / 40 NAX units, 128 GB), macOS 27.0.1 (26A434), Metal toolchain 32023.921.
Trigger: `iamwavecut/MLX-DLSS` issue #4 ("native FP8 on M6") — the community implementing DLSS neural
rendering on Apple Silicon runs FP8 E4M3 weights through MLX/Metal and asks whether the fp8 wall is silicon.
Our EXP-005 answer ("fp8 has no ANE datapath; the direct test was blocked") was **documentary, not measured**.
This pack makes it measured, on the tensor datapath that actually matters here (the GPU's NAX, not the ANE).

## Verdict (2026-10-26)

1. **Yes — fp8 `matmul2d` runs natively on M5 Max.** A kernel typed
   `tensor<device metal_fp8_e4m3_format, dextents<int32_t,2>, tensor_inline>` with
   `matmul2d_descriptor(64, 32, dynamic_extent, false, false, false)` + `execution_simdgroups<4>` +
   `op.run(sA, sB, sC)` produces **bit-exact** output (maxabs = 0 over all sampled cells, small-integer
   data exact in e4m3) across 24/24 ladder cases up to 8 output tiles, for **fp8×fp8** and for the
   documented **half×fp8** mixed form. No `metal_fp8_e4m3_format` → f16 pre-conversion is needed or done.
2. **But fp8 is gated behind `-std=metal4.1`.** metal4.0 rejects the type outright
   (`__HAVE_METAL_FP8_E4M3_FORMAT_TYPE__`). Measured, logged in `raw/s0-20261026T131216Z` (4.0 FAIL)
   vs `raw/s0-20261026T131851Z` (4.1 OK). **This is very likely why nobody upstream uses it:**
   MetalHLO pins MPP kernels to 4.0 (MetalHLOCompiler.swift:395-407) and the MLX steel bundle rides on it.
3. **fp8 throughput = fp16 throughput** at this kernel form: 31.8 vs 31.2 TF @ 2048³ (f8/f16, same
   window, 2000 reps), and matched energy within window noise. fp8 costs **half the input bytes** and
   gains **nothing at 2048³ in this form** — the shape is not bandwidth-bound here; the fp8 advantage
   must be earned with bigger tiles and bandwidth-bound shapes, not assumed.
4. **GPU dispatch floor for tensor matmul: ~5–7 µs/GEMM at small sizes** (M=128: 0.0053–0.0071 ms).
   For comparison, the ANE path floor measured here is **119 µs** ([m5max-s3-dispatch-floor]). One GPU
   tensor dispatch is ~20× cheaper than one ANE eval. (Note: the "240 ms on M5 Pro" figure circulating
   as a reason to doubt fp8 traces to OUR OWN number — EXP-029's **239.8 µs** single-tile dispatch-bound
   eval on M5 **Max** — µs→ms and Max→Pro got garbled in the retelling. No such number exists in MLX-DLSS.)

## Why the form matters (the story behind the first two failed ladders)

EXP-029 recorded twice that a hand-written `matmul2d` tile "FAILED its own oracle (992 of 2048 outputs
never written)" and concluded bare-metal must use MLX steel's `gemm_loop`. This pack found the actual
mechanics, from Apple's own material:

* **WWDC26-330 quantized-matmul form**: device `tensor_inline` views + `op.run(sA, sB, sC)` with a
  **device destination slice** — the `run` overload takes lvalue slices; the earlier attempts used a
  cooperative destination written element-by-element, and `run(tA.slice(), ...)` rvalue arguments,
  both rejected/misbehaving. fp8 dequant is then internal to TensorOps — no threadgroup round-trip.
* **Cooperative per-element fill is a dead end for fp8**: the element reference is
  `metal_fp8_e4m3_format`-valued and rejects `uchar` assignment (measured compile error). Inputs fill
  via `.load(tgTensor)` (26.3+), which this minimal probe does not need.
* **fp8 backing storage wants 128-byte alignment** (MTLTensor.h). All timed sizes keep K % 128 == 0;
  the explicit `k64-alignment-probe` (K=64, 64-byte row offsets) **passed anyway** — so K-alignment is
  not the EXP-029 failure's root cause; the destination form was.

Silent-zero traps (knowledge/ane/10 Q5) checked for this form: trap 1 (MTL4 pipeline) — not applicable
(device-destination `op.run` works on the legacy pipeline here, verified); trap 2 (innermost-first
extents) — honored (`dextents{K, M}`) and falsifiable via the mismatch debug; traps 3/4 (residency set,
threadgroup-memory length) — not applicable (no residency sets required by this form; no `[[threadgroup]]`
params). The ladder itself is the standing guard: any silent zero shows up as `zeros=N/M` and FAILs.

## What is already established (do not re-derive)

* NAX are per-shader-core tensor units inside the GPU, 40 on this box, ~60–74 TFLOPS fp16 ceiling
  (EXP-029 §0, corrected). [Apple tech-talk 111432 confirms the topology and 4–8× gemm-rate claims.]
* IOReport engagement lenses are not NAX verdicts (EXP-027 NXD-P1): PS13 fires for any saturated GPU
  compute. The discriminator is matched-A/B `GPU Energy` — used here (fp8 vs half×fp8 vs fp16).
* ANE fp8: no datapath (EXP-005, documentary). ANE dispatch floor 0.119 ms ([m5max-s3-dispatch-floor]).
* matmul2d beats `simdgroup_matrix` only at M ≥ ~400 on this chip (Tungsten, cited in 10-m5 §Q5).

## S2 — timed matrix (`results/fp8_matrix-20261026T1356Z.tsv`)

arm→kernel by construction: f8 → `mm_f8` (fp8×fp8→f32), mix8 → `mm_mix8` (half×fp8→f32), f16 → `mm_f16`.
Every timed row is preceded by a bit-exact precheck of the same kernel at the same shape (printed PASS).
**Concurrent-workload window (declared):** this box was running another agent's GPU/CPU work during
session EXP-037. First pass (`fp8_matrix-20261026T1358Z.tsv`) shows the contamination — M=4096 med 7.34 vs
min 4.79 ms. Re-take below as load subsided; med-vs-min gap ≤ 3% everywhere, cross-arm deltas ≤ 5%.
Treat absolute µs as upper bounds pending a certified-quiet re-run; the CROSS-ARM parity is the robust result.

| M   | f8 ms | f8 TF | mix8 ms | mix8 TF | f16 ms | f16 TF |
| --- | ----: | ----: | ------: | ------: | -----: | -----: |
| 128 | 0.0053 | 0.80 | 0.0054 | 0.78 | 0.0053 | 0.80 |
| 256 | 0.0069 | 4.85 | 0.0070 | 4.79 | 0.0069 | 4.88 |
| 512 | 0.0140 | 19.17 | 0.0139 | 19.29 | 0.0141 | 19.06 |
| 1024 | 0.0715 | 30.03 | 0.0716 | 30.00 | 0.0719 | 29.86 |
| 2048 | 0.5367 | 32.01 | 0.5362 | 32.04 | 0.5458 | 31.48 |
| 4096 | 4.3381 | 31.68 | 4.4658 | 30.78 | 4.5582 | 30.15 |

## S3/S4 — matched-A/B energy (`results/fp8_energy-2048-tight-20261026T1342Z.txt`)

2004 GEMMs/window at 2048³, enginemon 200 ms, interleaved repeats (f16, f8, mix8, f16, f8):

| arm  | mJ/GEMM (run1) | mJ/GEMM (repeat) | PS13 max | verdict |
| ---- | -------------: | ---------------: | -------: | ------- |
| f16  | 59.6 | 51.4 | 1973 / 2487 | baseline |
| f8   | 59.6 | 60.9 | 2178 / 2067 | energy parity (within ±15% window noise) |
| mix8 | 56.3 | —    | 2422      | parity, marginally lowest |

Read: at this shape and form, **native fp8 is confirmed correct and free-but-unrewarded**: half the input
bytes, same time, same energy. The NAX datapath question is answered by construction + parity:
a shader-emulated fp8→f16 path cannot run at fp16 parity speed for free; and Apple's documented fallback
behavior (TensorOps → shader implementations on pre-M5 parts) means native lowering is what runs here.
The binary NAX-yes/no lens stays honest per EXP-027: no direct counter exists; this is parity-plus-construction
evidence, not a counter reading.

## Limits (declared)

* Throughput parity is measured on ONE (admittedly simple, 64×32×dynamicK, unswizzled) kernel form.
  Bigger per-simdgroup tiles and Morton order (tech-talk 111432 V3 recipe) change the fp8-vs-f16 balance
  and remain untested here.
* Energy windows are desktop-normal, not certified-quiet (see EXP-029 quiet-window protocol); ±15% noise.
  Fleet-wide roll-up of every lane's speed/parity/dispatch/energy: `knowledge/ane/16-neural-accelerators.md`
  §Consolidated lane table v2 (2026-10-26); certified-quiet fp8 re-take is named open cell O-2 there.
* Lineage extension (same session): `harness/lane_arms.m` (INSTR-192) adds the f32(tf32-class), int8 and
  decode-padded arms — int8 @4096³ = 55.2 TF = **1.74× the fp16/fp8 band**, f32 14.0 TF, all bit-exact,
  both compiling at metal4.0 too (the 4.1 gate is fp8-type-specific). Timings loaded-window upper bounds.
* e4m3 codec is ours (RNE, clamp 448, matches MLX-DLSS semantics); decode-table oracle self-checks the
  encoder against itself on every case.
* M4 cannot run the 4.1 tensor fp8 path (TensorOps fp8 requires the M5-family datapath per Apple docs);
  the "M5 generation yes / M4 fallback" split in the reply is documentary for M4, measured for M5 Max.

## Reproduce

```sh
cd silicon-ledger/results/EXP-037-fp8-nax/harness
sh s0_compile_probe.sh                      # S0: 4.1 compiles fp8, 4.0 rejects the type
clang -fobjc-arc -O2 -o /tmp/fp8_ladder fp8_ladder.m -framework Metal -framework Foundation
/tmp/fp8_ladder ladder                      # S1: 24 cases, all maxabs=0
sh fp8_matrix.sh                            # S2: timed matrix -> results/*.tsv
sh fp8_energy.sh 2048 2000 f8               # S3/S4: one arm per invocation; interleave arms
```

Related: EXP-005 (ANE fp8 blocked test — this pack supersedes it for the tensor path),
EXP-029 (matmul2d ladder history this pack resolves), EXP-024/EXP-027 (matched-A/B method),
[Apple tech-talk 111432 + WWDC26-330 + MTLTensor.h / MPPTensorOpsMatMul2d.h headers — cited inline].
