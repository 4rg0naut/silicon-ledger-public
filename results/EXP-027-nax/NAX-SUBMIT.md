# NAX-SUBMIT — how data gets to the M5 GPU Neural Accelerators (measured 2026-10-08)

Plain-language answer to "how do we send data to this lane?", measured on
Mac17,14 (M5 Max), macOS 27.0.1 (26A434), CLT-only. Every claim below was run
on this box; raw windows in `raw/`, harnesses in `harness/`.

## TL;DR

There is **no separate "submit to NAX" call**. You submit ordinary Metal work —
bytes into an `MTLBuffer`; a `MTLTensor` is just a typed *view* of those bytes
(27.0 can back it explicitly with your buffer). The Neural Accelerators are
claimed **by instruction**: when a dispatched kernel executes a `matmul2d`
tile-operation, the hardware routes that tile onto the NA units inside the GPU
clusters. Your job is the buffer; the compiler+kGPU driver does the routing.

## The measured submission sequence (works on this box)

```
1  device   = MTLCreateSystemDefaultDevice()          # "Apple M5 Max", Apple9 family
2  buffer   = [device newBufferWithBytes:...]          # your bytes, Shared storage
3  tensor   = MTLTensorDescriptor{fp16, extents, usage=Compute}
             + MTLTensorBufferAttachments setBuffer:offset:forPlane:Data:
             -> [device newTensorWithDescriptor:attachments:error:]   # OK on 27.0
             # PITFALL (F-46): tensorSizeAndAlignWithDescriptor: SIGSEGVs unless
             # you set explicit `strides`; creation then wants strides NIL.
4  encode   = compute encoder; kernel args = the BUFFER (or MTLTensor for the
             MTL4 ML encoder); kernel body wraps pointer as metal::tensor and
             runs matmul2d_descriptor / matmul2d op over the tile
5  commit   = commandBuffer commit / waitUntilCompleted
6  readback = C buffer `contents` (Shared mode: CPU-visible after wait)
```

Verified pieces on this machine:
- steps 1–3 + 6 with the **system** runtime (NX-A probe, `p27_nax_probe.m`):
  tensor create OK (fp16 + fp8e4m3), buffer-backed tensor OK, `MTL4
  MachineLearningCommandEncoder` present as a protocol.
- step 4 (`matmul2d` kernel) compiles ONLY through **coreai's bundled compiler**
  — the system GPUCompiler 32023 on this box ships metal headers WITHOUT
  `matmul2d` (grep of its on-disk include tree is empty; `newLibraryWithSource`
  rejects it at both MSL 4.0 and 4.1). `xcrun metal` CLI absent (CLT-only).
- end-to-end via coreai `TorchMetalKernel` = the proven producer path
  (`harness/p27_load_coreai.py`, single valid tile 64×32×64 — see R8 note).

## Measured floors (single tile, this box, unprivileged)

| path | floor (median) | note |
|---|---|---|
| coreai matmul2d eval round-trip | **240 µs** (p10 227, p90 257, n=200) | CPU round-trip through coreai runtime, not GPU time |
| plain MSL dispatch+commit | **22.5 µs** (44,450/s sustained) | the submission floor of the raw Metal path |

## What the counters show when the lane works (honest lens table)

Windows: idle 4 s → matmul2d load (coreai) → plain-FMA MSL load 12 s → idle 4 s,
enginemon v2.1 unprivileged `--interval 500` (raw: `raw/p27_c_*.jsonl`, table:
`results/p27_counters.txt`).

| window | GPU Energy mean | ANE0 rail | ANE interrupts | GPU UT engagement counts (all perf states) | PS13 (top) |
|---|---|---|---|---|---|
| idle1 | 426 mW | 0 | 0 | 8,494 | **0** |
| matmul2d | **2,165 mW** | **0** | **0** | 19,982 | **8,387** |
| plain-FMA | **5,313 mW** | **0** | **0** | 47,340 | **47,000** |
| idle2 | 394 mW | 0 | 0 | 8,620 | **0** |

Readings:
1. **NAX traffic rides the GPU rail, not the ANE rail.** matmul2d load moved
   GPU Energy (+1.77 W mean) while every ANE channel (Energy Model ANE0,
   dart-ane0 interrupts, ANE-DCS-BW floor, ANE-LNK AF-BW) stayed at zero —
   the "GFX-ANE DCS lane" byte counters also stayed 0: those are ANE-client
   lanes, not NA-unit lanes. The GFX-DCS hypothesis is **refuted for
   NAX-matmul2d**; it stays open for true ANE work (AN-POS will test that).
2. **No per-NA-unit counter exists yet.** The closest lens we found: the
   `GPU UT AggD Stats` engagement channels' top perf-state bucket
   (Perf_State_13) — idle floor puts ZERO counts in PS13; matmul2d fill 8.4k
   counts. It is a GPU-wide "units were busy at max perf-state" signal, not a
   matmul-tile counter; treat as suggestive attribution, not a truth claim.
3. **The ANE zeros here say nothing about ANE routing** (unlike EXP-025/026
   catches): these loads never targeted the ANE, so 0 is expected on every
   channel. Channel validity for ANE loads = AN-POS criterion.

## Multi-tile recipe (MetalHLO @44b3a04, integrated 2026-10-08, WX-3)

Our R8 ladder says one tilegroup ever completes **via the coreai-compiler
route on this box**. MetalHLO (pedronahum/MetalHLO, pinned in
`knowledge/ane/SOURCES.md`) ships a working multi-tile MPP `matmul2d`
launch — they measure it on M5 Pro — so R8 is route-specific, not silicon.
Clone vendored hub-side at `tools/vendor/MetalHLO` (gitignored, EXP-026
convention) @`44b3a04`; build + compile-probe record:
`results/p27_metalhlo_build.txt`. Line refs below are that clone's
`Sources/MetalHLOCore/Compiler/CodeGenerator.swift`; pack pin excerpts:
`raw/research-2026-10-08/metalhlo_codegenerator_*.txt`.

Recipe, distilled (all line refs CodeGenerator.swift @44b3a04):

1. **Gate** — MSL 4.0 + Apple9 family only (`:3945`); fp32 goes to their
   NAX kernel (`:4013`), half/bfloat to MPP (`:4030-4034`, route dispatch
   `:4054-4070`).
2. **Tile geometry** — 128×128 tile = `execution_simdgroups<8>`, 256
   threads/TG; low-occupancy shapes (fewer than ~128 128-tiles vs ~64
   concurrent TGs) drop to a 64-tile/4-simdgroup/128-thread variant —
   matrix-coprocessor throughput per TG is unchanged, more TGs = better
   occupancy (`:4475-4490`, pick logic `:4030-4034`).
3. **Kernel body** — includes `metal_tensor` +
   `MetalPerformancePrimitives/MetalPerformancePrimitives.h`, `using
   namespace mpp::tensor_ops` (`:4395-4398`); plain `MTLBuffer` pointers,
   NO MTLTensor host API. `dextents`/`.slice()` are **(cols, rows)** —
   inner-stride dim first: A[M,K]→{K,M}, B[K,N]→{N,K}, C[M,N]→{N,M}
   (`:4408-4409`, generated ctors `:4595-4608`).
   `constexpr auto desc = matmul2d_descriptor(...)` then
   `matmul2d<desc, execution_simdgroups<NSG>> op; op.run(a, b, c);`
   (`:4426-4431`, `:4612`).
4. **Per-TG tiling = the multi-tile part** — one output tile per
   threadgroup via `A.slice(0, tgid.y*BM)`, `B.slice(tgid.x*BN, 0)`,
   `C.slice(tgid.x*BN, tgid.y*BM)`; K is not sliced (full reduction)
   (`:4614-4619`).
5. **Launch** — `gridWidth = ceil(N/tileN)`, `gridHeight = ceil(M/tileM)`,
   `threadgroupSize = tuning.blockSize` (256 for the 128-tile)
   (`:7091-7092`, `:7124`); batched = 3D grid depth=batchSize +
   `buffer(6)` batchCount with kernel-side `if (tgid.z >= batchCount)
   return;` guard (`:7128-7134`).
6. **Runtime compile** — MPP kernels must target
   `MTLLanguageVersion.version4_0` (their comment `:4266-4268`).

**This-box status**: `xcrun metal` is absent CLT-only (their own CLT build
dies the same way — mlx-swift `.metal` step, `unable to spawn process
'metal'`); under `DEVELOPER_DIR=/Applications/Xcode.app` the package
builds complete (792/792, 18.9 s) and our single-tile `matmul2d` probe
(`harness/p27_m2d_xcode_probe.metal`) compiles to AIR with `-std=metal4.0`
— the NX-B "no matmul2d headers" wall is **CLT-specific**, the Xcode 27
SDK carries `MetalPerformancePrimitives.framework/Headers/MPPTensorOpsMatMul2d.h`.
Next slice (correctness-only, checksum-gated): dispatch a multi-tile grid
from this AIR path and re-test the R8 ladder — no energy numbers until the
quiet-window rerun (user-run).

## Deviations / honest gaps

- armA capture window held 6.2 s of samples of ~22 s wall (interval dropouts
  during the wrapped load ramp); energy deltas remain positive-and-consistent.
- The `MTL4MachineLearningCommandEncoder` end-to-end data flow (tensor args ->
  NA execution -> result readback) was NOT exercised: the runtime MSL path
  cannot compile the tensor-op kernels here, and wiring MTL4 encoders+pipelines
  blind is out of scope for a measured doc. Next slice if wanted: MTL4Compiler
  route (headers on disk) — same unknown-header limitation likely applies.
- Floors are round-trip medians for identical shapes; GPU-internal tile time
  remains inside the (unlabeled) GPU energy delta until a sudo window pairs
  powermetrics rails with these windows.

## Reproduce

```sh
cd silicon-ledger
clang -fobjc-arc -o /tmp/p27_nax_probe results/EXP-027-nax/harness/p27_nax_probe.m -framework Metal -framework Foundation
/tmp/p27_nax_probe
clang -fobjc-arc -o /tmp/p27_load_msl results/EXP-027-nax/harness/p27_load_msl.m -framework Metal -framework Foundation
clang -O2 -o /tmp/p27_enginemon tools/enginemon/enginemon.c -framework CoreFoundation
/tmp/p27_enginemon --interval 500 --duration 16 --json --out /tmp/win.jsonl -- /tmp/p27_load_msl 12
.venv-conv/bin/python -u results/EXP-027-nax/harness/p27_load_coreai.py --seconds 4
# WX-3 matmul2d compile probe (needs Xcode 27, no sudo):
DEVELOPER_DIR=/Applications/Xcode.app xcrun metal -std=metal4.0 \
  -c results/EXP-027-nax/harness/p27_m2d_xcode_probe.metal -o /tmp/p27_m2d_probe.air
```
