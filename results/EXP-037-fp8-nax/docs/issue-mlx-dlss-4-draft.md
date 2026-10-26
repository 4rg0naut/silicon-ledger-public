# Draft comment for iamwavecut/MLX-DLSS issue #4 ("Any plans for native FP8 support on M6?")

Measured on M5 Max, macOS 27.0.1, bare-metal MSL (no MLX in the measurement path), 2026-10-26.
Source: our EXP-037 pack (kernel + ladder + timed matrix + energy A/B), reproducible in four commands.

---

**Native FP8 `matmul2d` works today on M5 — but it's gated behind `-std=metal4.1`, and the gate is
almost certainly why nobody's using it.**

We just measured the lowest layer directly (bare Metal tensor ops, no MLX runtime, exact-integer
oracle so any emulation artifact shows as a nonzero error):

* `tensor<device metal_fp8_e4m3_format, dextents<int32_t,2>, tensor_inline>` fed straight into
  `matmul2d_descriptor(...)` + `execution_simdgroups<4>` + `op.run(sA, sB, sC)` — **bit-exact**
  output, 24/24 multi-tile cases, maxabs = 0. Same for the documented `half × fp8` mixed form.
  The bytes your DLSS weights already carry go into the tensor units without any f16 pre-conversion.
* **Compile gate:** `-std=metal4.0` rejects `metal_fp8_e4m3_format` outright
  (`__HAVE_METAL_FP8_E4M3_FORMAT_TYPE__`); `-std=metal4.1` compiles it. MLX/MetalHLO pin their MPP
  kernels to 4.0 — which is why "MLX fp8" currently means dequant-to-f16, not the tensor datapath.
  An M5 path that raises the language version in the fp8 kernels gets the native datapath.
* **Throughput reality check @ 2048³, same kernel form (64×32 tile, unswizzled), re-taken as the
  co-tenant load subsided (declared: our box runs concurrent work; med-vs-min ≤ 3%):**
  fp8 32.0 TF vs fp16 31.5 TF vs half×fp8 32.0 TF — parity within 2%, same energy within
  measurement noise (matched-A/B GPU-energy windows, 2004 GEMMs each). fp8 costs half the input
  bytes and buys nothing at this shape; the fp8 win has to be earned with the big per-simdgroup
  tiles + Morton dispatch that Apple's M5 tech-talk demo (111432, their 7× headline) actually uses.
  Small-shape latency floor: ~5–7 µs/dispatch on the GPU tensor path.
* One retelling correction floating around: the "240 ms on M5" figure is our own **239.8 µs**
  single-tile dispatch-bound eval (M5 Max, not Pro, µs not ms). Nothing on M5 hardware says fp8 is
  a dead end; the hardware says it's free-but-not-magic at naive tiles.

So for the M6 question in the title: an M6 fp8 kernel would likely be a language-version bump plus
tuning, not new hardware required — with the caveat that we can't measure the fp8-vs-fp16 *delta*
difference between M5-NAX and M6-NAX from an M5 Max; happy to run the ladder on whatever harness
exposes M6 counter differences if someone with the device wants the methodology.

Repro (macOS 27, any M5): https://github.com/<your-ledger-mirror> — EXP-037/harness, 4 commands.

---

*Reviewer notes (not for posting):*
- Tone calibrated to "measured data, offered not lectured"; keeps the 240 ms correction light since
  it partially traces to our own published number.
- If maintainers engage, the follow-up artifact is the big-tile + Morton matrix (README "Limits").
- The M5 Max-vs-M5 Pro question in the original brief is deliberately not asserted — our data is
  Mac17,14 (M5 Max, 40 NAX).
