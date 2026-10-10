# NAX dossier v1 — activation, concurrency, memory paths (2026-10-10)

Companion to `README.md` (the bench protocol). Status tags: **[V]** measured by us on this box ·
**[D]** documented by Apple (pinned primaries) · **[S]** secondary/third-party · **[T]** to test in
EXP-029. Nothing tagged **[D]/[S]** is ours yet; nothing here is asserted as measured that was not
run here.

Sources (all pinned in-repo): `results/EXP-027-nax/raw/research-2026-10-08/` —
`wwdc2026_330_metal_tensors.html` (session 330 transcript + sample code), `mpp_programming_guide.pdf`,
`matmul.swift`, `tensor.swift`, `metalhlo_codegenerator_*`, `apple_mlx.html`, `arxiv_2606.22283v1.pdf`;
plus our own `results/EXP-0{24,25,27}-*/results/*`.

## 1. Activation surface — how you actually engage the units

There is **no dedicated activation call and no unit selector** anywhere in the public surface: the
units are engaged by *instruction selection plus data placement* **[D + V]** (our EXP-027: "no
dedicated call — MTLBuffer bytes + `matmul2d` claim the NA units").

Two documented routes:

**A. Buffers-only (no host tensor API) [D/S].** Plain `MTLBuffer`s + `matmul2d` in MSL; requires
Metal language 4.0 and Apple9. This is our working multi-tile route (MetalHLO @44b3a04 bundling
MLX `gemm_nax`), proven to build with Xcode-27 — CLT lacks the MSL 4.0 headers.

**B. `MTLTensor` host objects (session 330 sample code) [D].**
```
MTLTensorDescriptor *d = [MTLTensorDescriptor new];
d.dataType = MTLTensorDataTypeMetalFloat8E4M3;      // fp8 E4M3 data
d.usage    = MTLTensorUsageCompute;
NSInteger dims[2] = {NumCols, NumRows};             // NOTE: (cols, rows) — inner-stride first
d.dimensions = [[MTLTensorExtents alloc] initWithRank:2 values:dims];
id<MTLTensor> t = [device newTensorWithDescriptor:d error:&err];
```
MSL side (`#include <metal_tensor>`): `tensor<device half, dextents<int,2>>`, or a *quantized
multi-plane* handle:
```
using scales_plane = tensor_blockwise<tensor_plane_scales, device metal_fp8_ue8m0_format, 32, 1>;
using mxfp8_tensor = tensor<device metal_fp8_e4m3_format, dextents<int,2>, tensor_handle, scales_plane>;
```
and the op itself:
```
matmul2d<matmul2d_descriptor(TILEM, TILEN, dynamic_length_v<int>, false, false),
         execution_simdgroups<4>> op;
op.run(tA, tB, tC);          // TensorOps handles dequantization automatically [D]
```
Apple's own guidance: *"In most cases, you should feed your quantized data straight into TensorOps
so that it can automatically utilize any available hardware acceleration"* **[D]**.

## 2. Data types and quantization (documented)

| item | value |
|---|---|
| fp8 data | `MTLTensorDataTypeMetalFloat8E4M3` [D] |
| block scales | `MTLTensorDataTypeMetalFloat8UE8M0`, plane type Scales, `blockFactors` e.g. **32×1** [D] |
| low-bit claim | "16-bit half-precision weights could be compressed down to just 4-bits" [D] — exact 4-bit formats **to enumerate [T]** |
| fp16 / fp32 | half; fp32 runs via **tf32** `relaxed_precision` [S: MetalHLO] |
| mixed precision | `half × half → float` overload fuses the output cast in-register [S: MetalHLO] |
| dequantization | handled inside `TensorOps.run` for quantized tensors [D] |

**Why Apple pushes this**: *"the inference stage is typically memory bandwidth bound, so compressing
the weights becomes necessary both to better fit models into memory and to save memory bandwidth"*
**[D]** — i.e. on this hardware the tensor units are positioned as a *bandwidth-relief* mechanism as
much as a FLOPs one.

## 3. Concurrency — how many units, how many can be busy

- **Units = GPU cores = 40 on this box [V]** (1 NAX per core; API-164). So the ceiling is 40
  concurrently engaged accelerators, not a fixed engine pool.
- **Per-threadgroup**: `execution_simdgroups<N>` with N ∈ {4, 8} (128-tile → 8 simdgroups/256
  threads; 64-tile → 4/128) **[D/S]**; per-op tile geometry 64×64 or 128×128; occupancy gates
  `(M/128)(N/128)·batch ≥ 128` (128-tile) or `≥16` (64-tile) **[S]**.
- **Open** [T]: whether a threadgroup's N simdgroups land on N *distinct* cores (expected, unproven),
  and what the achieved-TFLOPS-vs-tile-count curve's knee is (a knee near ~40 core-equivalents would
  be direct evidence of the 40-unit ceiling). This is arm C of the bench.
- Dispatch cost matters at small sizes: single-tile eval was **dispatch-bound at 239.8 µs [V]**.

## 4. Memory — how each lane reaches *one* unified pool

One physical pool, **three access paths**:

| lane | host object / path | measured on this box |
|---|---|---|
| CPU | plain host memory, Accelerate/BNNS | **273.5 GB/s** steady-state read [V] |
| GPU SIMT | `MTLBuffer` (shared or private), device address space | **561.6 GB/s** steady-state read [V] |
| **NAX** | tensor handles over the **same `MTLBuffer`s**; auxiliary (scales) planes are separate buffers; MSL4/Apple9; alignment M/N/K multiples of 8 **[D/S]** | buffer type is the GPU's — NAX adds no separate memory (it lives inside the core); bandwidth/TFLOPS **unmeasured** [T] |
| ANE | **IOSurface**-backed I/O sized to `BatchStride` (API-126); DMA lanes (API-137/140) | ANE cannot take an `MTLBuffer` directly |

Cross-lane bridging, measured **[V]**: a GPU compute kernel writes into an `IOSurface` and signals;
the ANE-side wrapper waits; CPU verifies contents — **500/500 iterations in BOTH directions, median
123 µs** (API-141). So the GPU↔ANE bridge is an IOSurface + a shared-event counter, not a copy
through host memory.

Implications for a **tailored multi-lane engine** (why this dossier exists):
- CPU↔GPU/NAX share memory through `MTLBuffer` (ideally `MTLStorageModeShared`, no copies);
  GPU/NAX↔ANE must go through an `IOSurface` with an event counter.
- NAX and SIMT consume the *same* buffers, so "which GPU datapath" is a per-op choice that costs no
  extra data movement — the only cost is dispatch and occupancy.
- Open [T]: does a **shared** (non-private) `MTLTensor` work, or does tensor usage require private
  buffers? Can NAX read an **IOSurface-backed** allocation directly (zero-copy all the way to ANE)?
  Are there alignment/stride constraints on the **scales plane** (beyond blockFactors 32×1)? Is NAX
  more *bandwidth-efficient per FLOP* than SIMT on the same buffers (the real "when to use it" test)?

## 5. Test list → EXP-029 arms (each becomes a record when run)

1. **Activation A/B** [T]: buffers-only vs `MTLTensor` for the same GEMM — identical numbers
   (correctness gate) and Δtime/Δenergy. Also confirm the documented silent-zero traps are real
   (legacy pipeline path, row-major extents).
2. **Dtype sweep** [T]: half, fp8-E4M3 (± UE8M0 scales 32×1), tf32 — accuracy vs CPU reference and
   achieved TFLOPS each.
3. **Concurrency curve** [T]: TFLOPS vs tile count at fixed total work (1…512 threadgroups) — find
   the knee; check for a ~40-unit plateau.
4. **Memory-path matrix** [T]: same GEMM with (a) private buffer, (b) shared buffer, (c)
   IOSurface-backed buffer; measure Δtime and peak bandwidth; then the zero-copy NAX→ANE question.
5. **Lane decision table** [T]: for shapes {M=1,128,512,2048} × {fp16, fp8} — best lane and the
   NAX/SIMT crossover, all checksum-gated.

## 6. Measurement gate — mandatory, before any arm (GOTCHAS-077)

Measured on this box, 2026-10-10 (`results/QUIET-STATE.md`): GPU idle power swings **25 → 104 mW
inside one 30 s window** (29 × 1 s samples: min 25.1 / median 26.9 / max 104.3), and three adjacent
5 s windows with an *identical* process set read **118.96 / 85.19 / 119.84 mW** — so oMLX presence
was **not** the variable, and each of those windows would have silently corrupted a benchmark.

Protocol: run `harness/quiet_probe.sh <label>` before and after every arm; require GPU idle power in
the **~25–30 mW** band for ≥10 s (and Δ ≤ ~20 % across the arm); run the **`-O0`** `canary` before
and after (a moved canary means the machine changed, not the workload); discard rather than report
any window with excursions. Background reality to expect: 18–20 Apple daemons resident
(`mediaanalysisd`, `photoanalysisd`, `photolibraryd`, `cloudd`, `bird`, `backupd`, nine
`mds_stores` + `corespotlightd`, `corespeechd`/`assistantd`, `aned`/`ANECompilerService`), with
`VTEncoderXPCService` observed at 11.9 % CPU in one snapshot.
