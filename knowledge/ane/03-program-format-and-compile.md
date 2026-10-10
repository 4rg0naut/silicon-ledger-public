# 03 — The ANE program: what it is and how a model becomes one

This file covers the compile half of the ANE stack: how a source model (PyTorch, ONNX, TensorFlow) becomes
an Apple intermediate representation, how that becomes a loadable program on disk, what those on-disk files
actually contain, and what the chip executes. It then covers the execution model underneath — cores,
partitioning, on-chip memory, tiles, and why a matrix multiply is compiled as a 1x1 convolution — and finally
the descriptor/register-level structure and which operations are actually reachable.

Confidence is marked inline. `MEASURED` = a number someone put an instrument on; `DOCUMENTED` = stated in
official Apple material or in a primary reference we read; `INFERRED` = our reasoning over those sources;
`CLAIMED` = asserted by a vendor or project without evidence we could check.

The honest summary up front: **the last two stages of the chain — Apple's program format and the silicon's
execution model — are reverse-engineered, not documented.** Apple documents the pipeline's endpoints (a
converted model in, an `MLComputePlan` out) and nothing in between. Everything below the `Espresso`/`ane`
boundary comes from decompilation and measurement by the community; the single deepest source is
Bryngelson's arXiv:2606.22283 (`DOCUMENTED` in that paper, `decompile-derived` per the paper's own provenance
marks), and the one source that measures the DMA engine's register file directly is Yoon's 2026 ANE DMA
write-up.

---

## 1. The pipeline: source model → MIL → ANE program → silicon

### 1.1 The stages

| # | Stage | What it is | Who does it | Confidence |
|---|---|---|---|---|
| 1 | Source graph | PyTorch / ONNX / TensorFlow model | you | — |
| 2 | Frontend IR | **MIL** (Model Intermediate Language) for Core ML; a *Core AI IR* (MLIR-based) for Core AI | `coremltools` / `coreai-torch` converter | DOCUMENTED |
| 3 | Compiler input | `model.mil` (MIL) or a **netplist** (`.espresso.net`) for the direct route | coremltools / Espresso runtime | DOCUMENTED (MIL) / decompiled-paper (netplist) |
| 4 | Compiled program | dispatch descriptor + hardware container (`model.hwx`), or `.aimodelc` for Core AI | `ANECompilerService` / `coreai-build` | decompiled-paper + MEASURED (we inspected the artifacts) |
| 5 | Loaded image | the container with relocations resolved | kernel loader, signed | decompiled-paper |
| 6 | Execution | task-descriptor register writes drive the MAC array and DMA engines | firmware + silicon | decompiled-paper |

### 1.2 Core ML route (the supported one)

Core ML's own description (`DOCUMENTED`, developer.apple.com/documentation/coreml):

> "Core ML provides a unified representation for all models… Core ML optimizes on-device performance by
> leveraging the CPU, GPU, and Neural Engine while minimizing its memory footprint and power consumption."

and

> "If your app integrates AI models using the latest architectures and inference techniques, see Core AI."

The compute-unit setting is explicitly a *hint*:

```swift
let config = MLModelConfiguration()
config.computeUnits = .all        // "a hint, not a guarantee"
let model = try MyModel(configuration: config)
```

`DOCUMENTED` (neural-engine `running-on-ane.md`, Apple's docs). Converter side:

```python
import coremltools as ct
mlpackage = ct.convert(traced_model, convert_to="mlprogram",
                       inputs=[...], compute_units=ct.ComputeUnit.ALL)
mlpackage.save("Model.mlpackage")
```

`DOCUMENTED`, from Apple's own ANE-transformer reference article and repo (`ml-ane-transformers/README.md`).
The conversation goes PyTorch → TorchScript → MIL → `mlprogram`; the intermediate language is the host-side
handoff, and — per the paper — **fusion does not happen in MIL**: a biased+activated convolution arrives as
three separate ops (`conv`, `add`, `relu`) and is collapsed later inside `ANECompiler`
(`ZinIr`/`ZinMir`), decompiled-paper.

Apple's published picture of the hardware is minimal but real (`DOCUMENTED`,
`machinelearning.apple.com/research/apple-neural-engine`, which redirects to
`/research/neural-engine-transformers`): the ANE shipped in the A11 (2017) at 0.6 TFLOP/s fp16, and the
2021 fifth-generation "16-core ANE" was "capable of 26 times the processing power, or 15.8 TFlops".
Apple also publishes the *design rules* that make a model ANE-shaped, which are effectively compile-guidance
for stage 2 (`DOCUMENTED`, same page):

- represent Transformer tensors in `(B, C, 1, S)` "because the most conducive data format for the ANE
  (hardware and software stack) is 4D and channels-first";
- replace `nn.Linear` with `nn.Conv2d`, mapping the sequence axis to the last axis;
- **the last axis of an ANE buffer is not packed** and "must be contiguous and aligned to 64 bytes";
- chunk large attention tensors and avoid reshape/transpose copies, which become real memory copies.

### 1.3 Core AI route (the WWDC-2026 successor)

Apple's Core AI keeps "convert once, run on ANE/GPU/CPU" but replaces `.mlpackage` + coremltools with a new
IR and compiler (`DOCUMENTED` in Core AI docs / WWDC 324+326, distilled in
`repos/coreai-model-zoo/knowledge/coreai-overview.md`):

```
PyTorch (re-authored)
  → coreai-opt (optional: palettize / quantize)
  → coreai-torch TorchConverter → Core AI IR
  → .optimize() → save_asset() → .aimodel
  → [Swift] CoreAI.framework on device, or AOT-compiled by `xcrun coreai-build compile`
```

The compile CLI and AOT flow are documented by Apple:

```
coreai-build compile <input.aimodel> [--output <dir>] [--platform iOS|macOS|...]
    [--min-deployment-version 27.0] [--preferred-compute gpu|neural-engine|none]
    [--architecture <arch> ...] [--expect-frequent-reshapes]
```

`DOCUMENTED` (`xcrun coreai-build compile --help`, reproduced in
`coreai-model-zoo/knowledge/aot-and-specialization.md`). Two names are both real: **`coreai-build` is the
verb, `aimodelc` is the compiler binary and the compiled extension.**

On-device, a shipped `.aimodel` is *specialized* for the device + OS version, in two transforms: (1) a core
set of compilation steps that segment, plan and optimize compute — "this is where most of the latency is";
(2) executable-artifact generation for the chosen compute units. The result is cached. `DOCUMENTED`, WWDC 326
quoted verbatim in the zoo note.

### 1.4 The compiler is an out-of-process service

Compilation does not happen in the calling process. It is a sandboxed XPC service,
`com.apple.ANECompilerService`, reached over an `NSXPCConnection`, whose single entry point is
`compileModelAt:csIdentity:sandboxExtension:options:tempDirectory:...:withReply:`. decompiled-paper
(arXiv:2606.22283 ch. 6). Practical consequence for us: a compile failure kills/restarts a **shared** service,
which is why the paper records that after a failed ANE compile you should wait ~15 s before the next one.

### 1.5 The direct route (five steps, no Core ML)

The paper describes reaching the engine below Core ML through the `e5rt_*` C dispatch layer exported from
Espresso. Five steps: **build a network description → compile to the engine's program format → load →
bind operand buffers → dispatch**, where compile/load happen once and bind/dispatch are the hot loop
(decompiled-paper):

```c
/* Compile: the runtime drives the out-of-process compiler. */
e5rt_e5_compiler_create_with_config(&compiler, config);
e5rt_e5_compiler_compile(compiler, model_path, options, &library);
/* Load */
e5rt_program_library_retain_program_function(library, fn_name, &function);
/* Bind */
e5rt_io_port_bind_buffer_object(in_port, buf);
/* Dispatch (hot loop) */
e5rt_execution_stream_encode_operation(stream, op);
e5rt_execution_stream_execute_sync(stream);
```

This route is undocumented, unsupported, version-fragile and not App-Store-safe; the operations the compiler
accepts need no entitlement, but the path itself does. The community reference for it is tinygrad's
`extra/accel/ane` (which the paper credits with recovering the HWX format and the `AppleH11ANEInterface`
IOKit path).

---

## 2. The compiled artifact

### 2.1 What Core ML writes

A compiled Core ML model is a **directory bundle**, `.mlmodelc`. Files we actually saw on this machine
(`MEASURED`, `/Volumes/data/local_ai_stack/.venv/lib/python3.13/site-packages/coremltools/modelrunner/ModelRunner/add_model.mlmodelc`):

```
add_model.mlmodelc/
├── model.mil            ← the MIL program text ("program(1.0)" + buildInfo header)
├── coremldata.bin       ← binary metadata: I/O descriptions, hashes
└── analytics/coremldata.bin
```

`model.mil` is plain text and starts:

```
program(1.0)
[buildInfo = dict<...>({{"coremlc-component-MIL", "3402.3.2"}, {"coremlc-version", "3402.4.1"}, ...})]
{
    func main<ios16>(tensor<fp1...
```

`MEASURED` (we read it). The `coremldata.bin` blob carries strings like
`com.github.apple.coremltools.source → torch==2.5.1` and `source_dialect → TorchScript`, the provenance of
the conversion. `MEASURED`.

**The ANE program itself is not in the shipped `.mlmodelc`.** It is produced by *specialization* at load
time on the target and cached in a nested bundle. On this machine every ANE-bearing system model we looked
at has the shape:

```
<VAD|encoder>.mlmodelc/
├── model.mil.config                 ← procedure description (input/state shapes)
├── weights/weight.bin               ← (empty in the system models we inspected)
└── model.specialization.bundle/
    └── H16G.bundle/
        ├── H16G.e5                  ← dispatch descriptor (FlatBuffer)
        └── main/main_ane/model.hwx  ← THE PROGRAM (Mach-O-shaped)
```

`MEASURED`
(`/System/Library/AssetsV2/com_apple_MobileAsset_UAF_Siri_Understanding/purpose_auto/8f24c5d784dbd320bb3ae748e2d7d871fb61616e.asset/.AssetData/VAD.mlmodelc`).
Note the directory names: the target/arch (`H16G`), the callable procedure (`main`), and the engine-specific
sub-directory (`main_ane`). The procedure name inside the container is literally `main_ane`.
`model.mil.config` for that VAD model is a text file naming the input, 29-frame window, and five state
shapes — `MEASURED`.

### 2.2 `model.hwx` — the ANE program

`model.hwx` is **Mach-O-shaped but not Mach-O**: magic `0xbeefface` where a real 64-bit Mach-O would have
`0xfeedfacf`; `cputype 0x80` (an engine pseudo-architecture) and `filetype 2` (executable). Its content is a
register-write program plus weight coefficients. We parsed two of the 65 `.hwx` files under `/System/Library`
(`MEASURED`, our own parse):

```
cnn_frame_enhancer_96p.H17.espresso.hwx   size 933,888   magic 0xbeefface  cputype 0x80  cpusubtype 9  ncmds 37
  __PAGEZERO  (vmsize 0x4000)
  __FVMLIB ×11 (sections __const/__data, fileoff/filesize = 0 → no on-disk bytes)
  __DATA      (__bss)
  __TEXT      fileoff 0x14000 filesize 0x10000   sects __text, __const
  __KERN_0    fileoff 0x24000 filesize 0xc0000   sects __kern_0
```

and for the Siri VAD `main_ane/model.hwx` (901,120 bytes): 44 load commands, `__FVMLIB` windows with
`filesize 0`, then `__TEXT` (`0x8000`) and `__KERN_0` (`0xbc000`), plus `LC_THREAD`-family commands.
`MEASURED`.

This matches the paper's decode of the format exactly (decompiled-paper, ch. 23): the `__FVMLIB` windows
"declare the input and output tensors with fileoff and filesize both zero: they have no on-disk bytes and
exist only as virtual-memory declarations that the kernel maps into the address-translation aperture at
submit time"; the window sections align to `0x4000` (16 KiB DART page granule), the task-descriptor and
weight sections to `0x40` (64-byte engine tile granule). The paper's decoded 64 KiB sample is a Mach-O
variant: "patching those four bytes lets `otool` and `rabin2` parse the file, while the in-kernel loader
accepts the engine magic directly."

The container header (paper, decompiled):

| Offset | Field | Value | Meaning |
|---|---|---|---|
| 0x00 | magic | `0xbeefface` | engine compute executable |
| 0x04 | cputype | `0x80` | engine pseudo-architecture |
| 0x08 | cpusubtype | `0x4` | the H13 codegen revision |
| 0x0c | filetype | `0x2` | executable |
| 0x10 | ncmds | 15 | load-command count |
| 0x14 | sizeofcmds | `0x32d8` | load-command bytes |

Our own parses confirm magic/cputype/filetype and that `cpusubtype` tracks the codegen revision per target
(`9` on an H17 bundle, `7` on an H16G bundle, `4` on the paper's H13 sample). `MEASURED` (ours) for the
values, decompiled-paper for the interpretation of `cpusubtype` (our H16/H17 reading is INFERRED from the
monotone pattern, not decoded).

**What is inside the container's sections** (decompiled-paper):
- `__TEXT/__text` = the **task-descriptor register-write stream** (sparse, 44-byte records);
- `__KERN_0/__kern_0` = the **weight coefficients**, tiled for the streaming datapath;
- `__FVMLIB` = zero-byte virtual-memory declarations for the I/O apertures;
- a symbol table, the element-type catalog, per-tensor stride frames ("stabs-style" `s<stride><axis>`),
  a build-info banner recording the exact compiler invocation, and an `LC_THREAD` trailer holding procedure
  and tensor names (`main_ane`, `t0_ane`, `t5_ane@output`).

Weight tiling is fixed: **convolution weights at a `0xC0` stride, matrix-multiply weights at a `0x40`
stride**, each weight split into `min(8, lanes)` 64-byte-aligned tiles named `K<sha256>_ne_<i>`, with
empty sentinel tiles for unused lanes. Because the tiling is fixed, a **weight-value edit leaves the program
descriptor unchanged** — you can patch new weights into an already-compiled program. decompiled-paper.

The build-info banner from the paper's decoded sample is a real compiler invocation and is worth keeping:

```
-t h13g                                    target H13, the M1 engine
--fl2-cache-mode=resident                  keep the L2 working set resident
--fkernel-rewind=enabled                   kernel-stream rewind
--split-kernel-section=true                split the weight section
--max-kernel-section-size=134217728        128 MB weight-section ceiling
--e4m3-overflow-setting=Saturate           fp8 overflow policy: clamp, not NaN
--memcache-size=4194304 --bss-limit=3221225472
-foptimize-ne-utilization=true --enable-global-cw-optimization=true
-i .../model.mil -o .../model.hwx.tmp
```

Toolchain named in it: `zin_ane_compiler v9.509.0`, MIL component `3520.4.1`. decompiled-paper.

### 2.3 The dispatch descriptor (`.e5`)

Next to `model.hwx` sits a FlatBuffer: on this machine, `H16G.e5` (14,032 bytes). Its first bytes are

```
1400 0000 0000 0000 0c00 1400 0400 0800 0c00 1000 0c00 0000 ...
```

`MEASURED` (ours). Those vtable bytes `0c00 1400 0400 0800` are exactly the vtable the paper reports for the
dispatch descriptor ("FlatBuffer, vtable `0c00 1400 0400 0800`"). This is one of the cleaner cross-checks in
this file: an artifact from a shipping macOS release on our machine matches a decompiled schema in the paper.

Recovered schema (decompiled-paper; recovered from the `E5Serializer` symbol family, not from reflection,
because the runtime strips the binary schema):

```
table E5Program {
  symbol_names: [string];   // operation, tensor, section names
  build_info: BuildInfo;    // compiler version and source path k/v
  sections: [Section];      // per-operation arg_frame + op_attrs refs
  format_version: int;      // observed == 4
}
enum OpType : ubyte {
  Cast, AneInference, EirInference, CpuInference, BnnsCpuInference,
  MlcCpuInference, MpsGraphInference, E5MinimalCpu, Quant, Dequant,
  Barrier, JitCall
}
```

The canonical shape is **`Cast → AneInference → Cast`**: the whole fused graph is *one* `AneInference`
operation bracketed by format casts that convert the host fp16 layout to the engine's internal interleaved
layout and back. Two structural properties follow (decompiled-paper):

- **depth-invariant** — a 1-op graph and a 6-op fused graph both reduce to a single inference operation;
- **it tracks dispatch count, not operation count** — a bridge op that cuts the graph into 3 segments gives
  3 inference operations and a larger descriptor.

Per-operand layout is a fixed record (`TensorDescriptor`: `dim[4]`, `stride[4]`, width/height/channels/
batch/sequence_length, their strides, and an `int32 storage_type` code) — recovered verbatim from a runtime
type-encoding string; the two leading pointers are runtime-only and not serialized. decompiled-paper.

Element-type codes in the serialization space are a closed set of eleven: `0 int4, 1 uint8, 2 int8,
3 float16, 4 float32, 5 int16, 6 uint16, 7 int32, 8 uint32, 9 int64, 10 uint64`. decompiled-paper. (The
*hardware* catalog in the container symbol table is wider — 24 entries — because it also holds fp8 forms and
palettized index types.)

### 2.4 What Core AI writes

Two artifact kinds, both directory bundles, and we have both on this machine.

**`.aimodel` — the portable IR** (`MEASURED`, `/Volumes/data/local_ai_stack/work/exports/von-retest/von-1.0_v1_float16_s256_ane.aimodel/`):

```
metadata.json   450 B    {license, author, description, assetVersion "2.0",
                          producer "coreai-core 1.0.0b2", creationDate}
main.mlirb      792,214,837 B
main.hash       32 B
```

`main.mlirb` is **MLIR bytecode**: first bytes `4d4c ef52 0d4d 4c49 5232 322e 302e 3067 6974` =
`ML\xefR` + `MLIR22.0.0git`. `MEASURED` (ours). It is a flat buffer with the weights inlined: the
companion AOT `stats.json` reports `Float16 count = 395,899,912`, and 395,899,912 × 2 = 791,799,824 bytes,
which is essentially the whole 792 MB file. `MEASURED` (ours). Model: Von-1.0, a ModernBERT-Large
non-autoregressive decision model re-authored for the ANE at S=256.

**`.aimodelc` — the AOT-compiled artifact** (`MEASURED`, `von-retest/aot/von-1.0_v1_float16_s256_ane.h16g.aimodelc/`):

```
metadata.json   538 B   producer "coreai-build-3600.83.1", sourceHash, assetVersion "2.0"
stats.json      1,470 B graph statistics (see below)
main.hash       32 B
main-h16g.mlirb 1,628 B
main-h16g-delegates/
  MPSGraph/mpsExecutable.mpsgraphpackage/
    manifest.plist                    31,146 B  (Package Version 7.0.63, ANERegionsHash per arch)
    original_model_0.mpsgraph        309,404 B
    specialized_model_1.mpsgraph     250,537 B
    resources.bin                791,809,168 B  ← the weights
    binary_0.llir.bundle/
      Manifest.json
      main_<hash>_0_ANE_region_0_0.bc/
        main_<hash>_0_ANE_region_0_0.bc.weights
        h16g/main_<hash>_0_ANE_region_0_0.mlir.bc   ← the ANE region as MLIR bytecode
```

`MEASURED` (ours). The layered structure is worth reading carefully:

- the AOT compile *folds the model into an MPSGraph delegate*; even with `--preferred-compute neural-engine`
  a delegate is emitted;
- the delegate carries the graph as `.mpsgraph`, the weights as `resources.bin`, and the ANE part as an
  **ANE region of MLIR bytecode** (`..._ANE_region_0_0.mlir.bc`) with its own `.bc.weights`;
- `Manifest.json` in `llir.bundle` and `manifest.plist` record the `ANERegionsHash` keyed by arch (`h16g`);
  the compilation descriptor in `manifest.plist` shows `"useANELLIR" : true`,
  `"enableANECValidationWorkflow" : true`, `"shapeShifterCacheThreads" : 1`, `"optimizationLevel" : 1`.
  `MEASURED` (ours).

So on the Core AI path, "the ANE program" that a reader can see on disk is an **ANE region in MLIR
bytecode**, not an `.hwx`. Whether the region is later lowered to the same HWX/task-descriptor form the Core
ML path produces is `OPEN` — the paper's container decode is for the Espresso/Core ML path, and the Core AI
compile bundles an MPSGraph executable around the engine part. `INFERRED` (ours): the engine-side format is
almost certainly shared (see §4 cross-checks), but we have not seen an `.hwx` produced by `coreai-build`.

The number of ANE regions is a directly measurable property of the compiled artifact, and it is the load-time
lever:

```bash
find <bundle>.aimodelc -name '*ANE_region_*.mlir.bc' | wc -l
```

On Apple's own ANE authoring rules (`coreai-model-zoo/knowledge/compute-units-and-authoring.md`, MEASURED by
that project): a Parakeet FastConformer encoder produced **49 ANE regions** authored for the GPU and **25**
re-authored for the ANE, and that halving showed up as **65.7 s → 11.9 s cold** and **2.2 s → 0.59 s warm**
load — not as steady-state speed. Which is the practical statement of what the compile step buys you.

`stats.json` from our Von AOT bundle is the clearest evidence of what the compiler still sees on the ANE
path (`MEASURED`, ours — full file read):

```
storageTypes: Float16 395,899,912 | Bool 65,536 | UInt32 75 | Int32 36 | Float32 2 | UInt64 1
computeTypes: Bool, Float16, Float32, Int32, UInt32, UInt64
operationDistribution (top): constant 1624, reshape 297, slice 253, broadcast_in_dims 235, mul 235,
  broadcasting_mul 231, transpose 198, add 179, batch_matmul 170, broadcasting_batch_matmul 170,
  concat 169, broadcasting_add 145, broadcast_to 123, split ...
```

Two things to notice: the graph the compiler is handed is dominated by **layout ops** (reshape/slice/
transpose/concat/broadcast) around a comparatively small number of `batch_matmul`s — which is exactly the
"avoid reshape and transpose, they cost copies" rule from Apple's own guidance; and the *only* numeric work
in the storage census is Float16 (plus 2 Float32 and 76 integer scalars).

### 2.5 Other formats you will meet

| Format | Where | What | Confidence |
|---|---|---|---|
| `.mlpackage` | converter output | source + `model.mil` + weights, pre-compile | DOCUMENTED |
| `.mlmodelc` | compiled Core ML bundle | `model.mil`, `coremldata.bin`, `weights/` | MEASURED (ours) |
| `model.specialization.bundle/<ARCH>.bundle/<proc>/<...>_ane/model.hwx` | Core ML ANE program on disk | the Mach-O-shaped engine executable | MEASURED (ours) |
| `<ARCH>.e5` | Core ML ANE dispatch descriptor | FlatBuffer, `format_version` 4 | MEASURED (ours) + decompiled-paper |
| `.aimodel` | Core AI portable IR | `{metadata.json, main.mlirb, main.hash}` | MEASURED (ours) |
| `.aimodelc` | Core AI AOT output | `main-<arch>.mlirb` + MPSGraph delegate with `ANE_region_*.mlir.bc` | MEASURED (ours) |
| `.espresso.hwx`, `.espresso.net`, `.espresso.weights` | legacy Espresso assets in the OS | engine programs by generation (`cnn_frame_enhancer_*.H13…H17.espresso.hwx`) | MEASURED (ours) |
| `.mlmodel`, `.mil`, `.espresso.net` | old / direct route | netlist input the compiler also accepts | DOCUMENTED / decompiled-paper |

Inventory note (`MEASURED`, ours): **65 `*.hwx` files under `/System/Library`** on this machine, including
`cnn_frame_enhancer_*.H13/H14/H15/H16/H17.espresso.hwx` in `VideoProcessing.framework` — i.e. one program
per engine generation for the same filter, which is the on-disk proof that a compiled program is
target-specific.

---

## 3. The execution model, as far as it is publicly understood

### 3.1 Cores — and why "16" is contested

Apple's published figure is **16 cores** (`DOCUMENTED`, ML research: "the fifth-generation of the 16-core
ANE"). The paper's decompilation says the *compiler's* per-die core count lives at HAL offset `0x238` and is
a **different quantity**: 4 on the M1 base, 8 on `g` parts, 16 on `s`, 32 on `c`, 64 on `d`. The paper is
explicit: "These decoded `num_nes` values are the compiler's per-die core field, not Apple's marketing Neural
Engine count; on the base M1 the decoded four stands against the published sixteen." decompiled-paper.

Meanwhile the DMA write-up, working on M3, states plainly "ANE has 16 cores in parallel. Cores divide work by
partitioning a buffer evenly across N cores", and derives that from the register file actually containing **16
core base/size register pairs** (`TD+0x078` … `TD+0x0b4`, then 16 size words at `TD+0x0b4–0x0f0`), with
sweeps showing latency constant from 1 to 16 active cores. `MEASURED` (Yoon, on M3).

These are not necessarily contradictory — 16 hardware partitions vs. a small number of independently
power-gated compute sets vs. a compiler-visible `num_nes` are three different layers, and the paper itself
measures a ~10 mW step **per core** over an ~800 mW floor matching "four independently power-gated compute
sets, one per core" on M1. But no source we have reconciles them explicitly. Treat the core count as
**layered and partially contested**; do not write "the ANE has N cores" without saying which layer you mean.

One more number to keep separate, from the paper: a live M1 compile costs against **8 active engines on 1
cluster**, with candidate split geometries of 1, 4, and 16 engines speculated — "a model-internal figure
rather than the registry core count". decompiled-paper.

### 3.2 How work is partitioned across cores

The dimension the compiler splits across cores is **output channels**, by strided round-robin
(decompiled-paper, `ZinMirNECoreAssignment`):

```
core(c) = c mod N          # channel c -> core c mod N   (N = 4 on M1)
ocg_passes(c_out, ocg) = ceil(c_out / ocg)
cores_needed = min(N, next_pow2(ceil(c_out / ocg)))
```

The active-core count is **shape-driven, not user-selectable**: it is derived from the output-channel count
and the output-channel-group size, rounded up to a power of two, and written into the task descriptor's
3-bit `ActiveNE` field. Measured scaling on M1 is linear-integer (1→4 cores: 3.8, 7.6, 11.4, 15.4 GMAC/s).
decompiled-paper.

Note the friction with the DMA write-up's framing: Yoon describes cores as taking *slices of the weight
buffer* ("each core handles N/16 kernels"); the paper describes them as taking *output channels*. On a
Conv/GEMM these are the same partition viewed from the weight side and the output side. `INFERRED`.

### 3.3 On-chip memory: "L1" kernel memory, the L2 working set, and the 64 banks

Three on-chip numbers matter, and they appear under different names in different sources.

**(a) Kernel memory ("KMem", the weights) — 64 KB.**
The DMA write-up says "the resident 'L1' KMem is 64 KiB per core". `MEASURED` (Yoon, M3). The paper
independently puts a **64 KB kernel-coefficient store** on the M1 (`0x200`/`0x210`, with the 64 KB-or-16 MB
mode select at `0x288`) and a 64-unit kernel-memory budget in the cost model; the per-chip numeric-limit
table lists **kernel-memory budget 64 KB** for every family from A13 through A16/M5. decompiled-paper.
Two independent methods, same number — this is the best-corroborated structural fact in this file.

**(b) The L2 / operand working set — 2 MB on M1, ~4.72 MB on M5.**
The paper: the largest single operand that stays in on-chip SRAM is **2 MB** (`HAL[0x1b8]`, aliased
`MemCacheSize`/`L2Size`); above it the operand is tiled and streamed from DRAM. The measured throughput
threshold sits slightly higher, **2.28–2.34 MB**, because the tiler holds ~0.3 MB of double-buffer margin.
Below the bound the resident operand must fill before compute starts; above it the tiled path
double-buffers, so throughput *rises* across the threshold (992 → 1226 GFLOP/s between 2.28 and 3.00 MB).
On the M5 the bound is ~4.72 MB (that value also appears in
`coreai-model-zoo/knowledge/ane-silicon-reference.md`). decompiled-paper + MEASURED by that paper.

**(c) Banks — 64 banks, 16-byte granule.**

```
bank(addr) = (addr / HAL[0x1c0]) % HAL[0x1c8]      # (addr / 16) % 64 on M1
```

The pool is a compiler-managed scratchpad, **not a demand-filled cache**: residency and stride are decided at
compile time and written into the program, so the order in which weights are re-referenced does not change
what is resident. The bank-conflict optimizer picks the row stride with the least per-bank cost over a
64-entry cost vector, and never proposes a stride above the 2 MB ceiling (`0x1f8`). decompiled-paper.

Alignment scales coexist (decompiled-paper, ch. 21): **16 B** DMA-width granule (`0x1c0`), **256 B** segment
alignment, **16 KB** DART page at which buffers map into the engine, and **64 B** engine tile granule for
task-descriptor/weight sections inside the container.

The invariant across all of this: **the array is fed from a scratchpad the compiler schedules, not from a
cache the hardware manages.** Almost every "keep it under X" rule for ANE work (keep the largest operand
under 2 MB; keep the last axis contiguous; don't add reshape copies) is a consequence of that one fact.

### 3.4 Tiles

The per-core geometry (decompiled-paper): an **accumulator budget of 8** work units; output channels are
tiled into **output-channel groups (OCG)** sized by

```
OCG = min( floor_pow2( 8 / (kW·kH·kD) ), byte_cap )
```

with `byte_cap` = 32/16/8 bytes per kernel element depending on weight format. A 1x1 convolution has
kernel-element count 1 and so admits a *large* group; a 3x3 has 9 and needs roughly 9x more passes over the
input. Lane widths: **4 output channels/cycle fp16, 8 int8** (and 2 or 1 in narrow "small/tiny source"
modes). The pass count is `ceil(Cout / OCG)`; the measured signature is a super-linear cost step when it
increments, e.g. a 1x1 fp16 conv at 32x32 going from ~20 µs to ~61 µs per layer between Cout 192 and 256.

The task descriptor's own field widths encode the shape caps directly: **spatial dims are 15-bit**
(`Win @0x0f4 mask 0x07fff`), **channel dims 17-bit** (`Cin @0x100 mask 0x1ffff`, i.e. up to 131071), and
`OCGSize` is 3-bit. decompiled-paper. That is why a 65536-wide channel axis is fine while a 32768-wide
spatial axis is not — and why the last-axis alignment rule matters more than the rank cap in practice.

### 3.5 Why a matrix multiply is a conv1x1

Three independent statements of the same fact:

- **Compiler mechanism** (decompiled-paper): the pass `ReplaceMatmulWithConv` rewrites a matrix multiply or
  linear *whose right-hand weight fits the on-chip working set* into a resident convolution; above the 2 MB
  ceiling it stays a tiled matrix multiply. Convolution is the native array datapath; matmul folds into it.
- **Apple's own authoring guidance** (`DOCUMENTED`, ML research + `ml-ane-transformers`): "we swap all
  `nn.Linear` layers with `nn.Conv2d` layers", with a `load_state_dict_pre_hook` that unsqueezes the linear
  weights to the conv weight shape.
- **Compiler-side rule** (paper, ch. 17): replace a fully-connected layer with an equivalent 1x1 convolution
  "so it runs on the convolution datapath"; a linear `y = x @ W.T` over `Cin → Cout` is the same arithmetic
  as a 1x1 conv.

The arithmetic is identical; what changes is that the conv datapath carries the foldable epilogue (bias,
activation, quantize) and has an OCG tiling rule that a 1x1 kernel maximizes (kernel-element count 1 ⇒
largest group). `INFERRED` for the "why this particular choice" part; `MEASURED`/decompiled for the
mechanism.

The orientation is part of the format: Apple's guidance is that the sequence axis should be **width**
(`(B, C, 1, S)`), because the last axis is the unpacked, 64-byte-aligned one. Our own Von ANE export follows
the same rule (RoPE as buffers, layer-0 norm omitted, GELU MLP, mean pooling, classifier padded to 32 —
metadata.json, `MEASURED` ours).

---

## 4. Descriptors and register-level structure

### 4.1 Three layers of descriptor

The paper separates them cleanly (decompiled-paper, ch. 23, and figure 23.1):

| Layer | Format | Holds |
|---|---|---|
| Dispatch descriptor | FlatBuffer `E5Program` | the operation chain as parametric arg-frames + attribute blobs |
| Hardware container | Mach-O-shaped, magic `0xbeefface` | register-write stream, weights, typed I/O layout |
| Hardware task descriptor | flat register image (`ZinAneTdHw_v10` on M1) | the register groups that configure the DMA engines and the array |

The middle layer carries the *parametric* description; the **actual register image is materialized below the
host boundary at load** — "the loader expands the parametric descriptor in the bundle into the explicit
register-write program… so the shape-specific program appears in no host buffer". decompiled-paper. That is
why the descriptor size does not grow with the compute shape (byte diversity 0.19; a contraction over inner
dim 64 and one over inner dim 256 produce the same descriptor size).

### 4.2 The hardware task descriptor's seven register groups

Version-10 layout as decoded for the M1 (decompiled-paper):

| Group | Struct base | Registers | Register base | Contents |
|---|---|---|---|---|
| Kernel and common | +0x2c | 34 | 0x5500 | kernel-DMA enable, format, stride, task type, network id |
| Dimensions | +0xfc | 19 | none | input/output W, H, D, C, groups, transpose, interleave, OCG size |
| Tile DMA | +0x150 | 69 | 0x4d00 | three tile-DMA engines: enable, cache hints, base halves, strides, format, wrap |
| Element-wise and planar | +0x26c | 30 | 0x4100 | elementwise/planar config, padding mode |
| L2 and texture | +0x2ec | 14 | 0x4500 | L2 source/result config, texture mode, source dims |
| Kernel format and op mode | +0x32c | 11 | 0x4900 | op mode, kernel alignment, sparse/palette flags, bias enables |
| L2 result | +0x360 | 21 | 0x5100 | L2-result base, strides, wrap, result format |

**Base addresses are not written at compile time.** Each is a *named relocation slot* keyed by a register
address, patched by the loader (decompiled-paper, v10 map):

| Relocation register | Slot |
|---|---|
| 0x1344 | input tile read base |
| 0x134a | second-operand read base |
| 0x1442 | output tile write base |
| 0x1554 | kernel bias stream |
| 0x1558 | kernel post-scale stream |
| 0x155c | kernel palette-lookup stream |
| 0x1560 | kernel activation-lookup stream |

The four weight sub-streams exist because a fused convolution emits its bias, post-scale (where a
dequantize scale folds), palette LUT and activation LUT as **four independent coefficient streams**, each
with its own relocation slot. A convolution with batch-norm and a following activation therefore does not
become four operations. decompiled-paper.

Field widths in that descriptor (decompiled-paper, listing 43):

```
Win     @0x0f4 mask 0x07fff    /* input width, 15-bit */
Hin     @0x0f6 mask 0x07fff    /* input height, 15-bit */
Cin     @0x100 mask 0x1ffff    /* input channels, 17-bit (up to 131071) */
Cout    @0x104 mask 0x1ffff
OCGSize @0x118 mask 0x07
numGroups @0x11c mask 0x1fff
```

Each DMA stride is a **26-bit signed field at bit 6** of its register word, range-checked against a
per-chip bound table. The serializer is **sparse**: a register reaches the stream only when its value differs
from the architectural default, and each surviving record is a fixed **44 bytes** — a count marker, the
register address in one IOMMU aperture, and one or two device addresses in a second aperture. decompiled-paper.

### 4.3 What the DMA write-up gives us, and how it lines up

Yoon's post is the only public source that prints actual task-descriptor words. On an M3 Air, holding
everything but the DMA size/address constant:

```
                                   D=2044      D=2048      D=2052
TD+0x004  estimated cycles         0x000001ea  0x000001eb  0x000001ec
TD+0x078  core 1 base              0x000ff800  0x00100000  0x00100800
TD+0x07c  core 2 base              0x001ff000  0x00200000  0x00201000
...
TD+0x0b0  core 15 base             0x00ef8800  0x00f00000  0x00f07800
TD+0x0b4–0x0f0  core sizes ×16     0x000ff800  0x00100000  0x00100800
TD+0x134  Common.Cin               0x000007fc  0x00000800  0x00000804
TD+0x1f0  L2 source stride         0x00007fc0  0x00008000  0x00008040
TD+0x1f4  unknown stride mirror    0x00007fc0  0x00008000  0x00008040
TD+0x214  L2 result base           0x00008fc0  0x00009000  0x00009050
```

`MEASURED` (Yoon). Structural facts to extract, independent of the erratum itself:

1. The descriptor contains **16 core base addresses** (`+0x078` stepping by 4 bytes) and **16 core sizes**
   (`+0x0b4–+0x0f0`) — the evidence for 16 hardware partitions on that part.
2. The core bases are **contiguous and equal-sized**: for D=2048 each core's slice is `0x00100000` = 1 MiB,
   and core *k*'s base is `k × 1 MiB`. Cores divide the weight buffer evenly. That is a direct measurement of
   the partitioning scheme from §3.2 seen from the DMA side.
3. `Common.Cin` (`+0x134`) = 0x800 = 2048 = D, and it tracks D. There is a "common" register block with the
   contraction width in it.
4. `+0x1f0` and `+0x1f4` are **L2 stride words** that track D with a 64-byte step; `+0x214` is an **L2
   result base**. Note the collision of meaning with the paper: the paper names `0x1f0` in a different space
   as the *resident-buffer threshold* (0 on M1, 32 KB on A15-class, 256 KB on A16/M5). `CONTESTED` — these
   are almost certainly two different address spaces (Yoon's `TD+0x…` is the M3 task-descriptor register
   image; the paper's `0x1f0` is a HAL *table* field). Do not conflate them.
5. The descriptor words are **not the same layout across generations**: Yoon is reading M3/H15-generation
   hardware; the paper's decoded struct is M1 `ZinAneTdHw_v10` with group bases at `+0x2c`, `+0xfc`,
   `+0x150`, … Any tool that reads task-descriptor bytes "must dispatch on the version number rather than
   assume a fixed layout" (decompiled-paper). `INFERRED` that the two offsets are simply different versions;
   neither source decodes the other's generation.

The erratum itself belongs in the gotchas file; the structural lesson here is that **the register image is
versioned per silicon family (14 versioned descriptor structs exist), sparse, relocation-based, and readable
from user space if you can get at the DMA path.**

### 4.4 Opcode words and operation classes

Two different "opcodes" exist: a *codegen* opcode word in the task-descriptor stream, and an *operation
class* in the descriptor.

Version-7 (H13) codegen opcode words decoded from a live M1 task-descriptor stream (decompiled-paper):

| Operation | Opcode word |
|---|---|
| Convolution | `0x5042a063` |
| Reduce-mean | `0x5000a021` |
| Matrix multiply | `0x5000b021` |

with the high half-word (`0x5042` / `0x5000`) shared and the low 16 bits distinguishing the operation —
and, importantly, "the full operation identity is also in the lookup-table and configuration words, not in
the opcode word alone". `ZinAneTd` records are chained by a **next-record pointer at `+0x1c`**, terminated by
a null, and each descriptor's weight bases live in an inline relocation array against `__KERN_0` rather than
in the header. decompiled-paper.

The operation-class enumeration (the descriptor's "operation mode") has **79 members**; representatives:

| Class | Code | Class | Code |
|---|---|---|---|
| Conv | 1 | MatrixMultiplication | 18 |
| Pooling | 2 | Reduction | 20 |
| Concat | 3 | Linear | 60 |
| ElementWise | 4 | NEConv | 68 |
| ScaledElementWise | 5 | NEMatMul | 69 |
| Neuron | 6 | NEPool | 70 |
| GOC | 8 | SDPA | 77 |
| Softmax | 24 | AllReduce | 78 |

decompiled-paper. Note there is **no transposed-convolution class** — a transposed convolution lowers to a
convolution, cross-correlation, or kernel rasterizer. And note `GOC` (the gain-offset control, i.e. the
fused `gain·x + offset`): the paper's fusion story is that the whole epilogue chain lands in
`ZinNEBypassLayer`'s seven slots —

```
ZinNEBypassLayer( engine_op,
    ZinTextureLayer,    // in-place spatial/texture remap
    ZinBroadcastLayer,  // broadcast of a fused operand
    ZinActivationLayer, // pre-GOC activation
    ZinGOCLayer,        // the gain/offset (scale + bias) unit
    ZinActivationLayer, // post-GOC activation
    ZinTransposeLayer,  // output transpose / layout
    ZinQuantLayer )     // output (re)quantization
```

The dividing line between "fuses" and "stays a real layer" is the guard `"Must have 2 inputs when convert EW
to GOC"`: an elementwise op with exactly one live operand and one constant can become a GOC (so bias-add and
scale fold in), while `add(conv_a, conv_b)` has two live inputs and remains a real `anec.add` layer.
Concat is a fusion boundary unless qualified, and scaled-dot-product attention is a **hard segment cut**.
decompiled-paper.

---

## 5. Opcode / op coverage: what the ANE actually runs

### 5.1 Three independent views

| View | Method | Numbers |
|---|---|---|
| Paper Appendix A | compile-and-run on M1/M2/M5 + decompile-derived prediction for M3/M4 | 187 MIL ops exposed; **~108 native on M1**; 9 need M2+; 4 need M3+; **37 rejected on every family**; ~24 compiler-internal |
| `ane-probe` on our M4 / macOS 27 | build a 1-op Core ML model per MIL op, query `MLComputePlan` | 168 scanned, **130 built**, **100 ANE-supported (76.9%)**, 38 skipped |
| `neural-engine/docs/unsupported-layers.md` | community experience, layer-level not op-level | a list of layer types that fall back |

Notes on each (`MEASURED`/`DOCUMENTED` as labelled):

- Paper Appendix A: "each native operation compiled and run and each no-path one rejected on the target",
  with M3 and the M4 half of the M4/M5 column being decompile-derived *predictions*, not measurements.
  `DOCUMENTED` (primary), and worth quoting for its method: *"Every operation marked native in Appendix A
  was compiled and run on the M1, not inferred from a capability bit."*
- `ane-probe`: `MEASURED` by us on this machine (M4, macOS 27.0, coremltools 9.0), recorded in
  `results/EXP-001-ane-op-map/`. Every row shows `preferred = CPU` and that column is **meaningless** —
  single-op models pay the ANE transfer cost, so the compiler prefers CPU; only `supported` is informative.
  Its 38 skipped ops are a probe limitation, **not** evidence about the ANE.
- Hardware-fallback lore: `neural-engine/docs/other.md` records the reverse: on A12+ a "smart compute
  system" may put an all-ANE-eligible model on the GPU anyway, especially when the GPU is idle.
  `CLAIMED` (anecdotal, with a cited tweet).

### 5.2 The native core (agreement across sources)

Convolution (2D, transpose/deconv, dilated, depthwise, grouped), matrix multiply / fully-connected, fused
scaled-dot-product attention, layer/instance/group/L2 normalization (batch-norm folds to an affine), pooling
(avg/max/L2), elementwise arithmetic and comparison, activations (ReLU family, sigmoid, tanh, gelu, swish,
softmax, erf, exp, log — implemented via a programmable piecewise-linear lookup table), and data movement
(reshape, flatten, expand, squeeze, transpose, concat, split, stack, constant pad, slice) as descriptor
edits or DMA rather than compute. `DOCUMENTED` (paper ch. 4) and consistent with our M4 scan, which found
every dense-transformer op ANE-capable: `matmul · linear · conv · add · mul · sub · softmax · gelu · relu ·
layer_norm · gather · transpose · reshape · reduce_mean · exp · erf · rsqrt · pow` (`MEASURED`, ours).

### 5.3 The no-path set, and the important distinction

Rejected on **every** family from M1 to M5, per the paper: `reduce_prod`; the scatter family (`scatter`,
`scatter_along_axis`, `scatter_nd`); `mod`; `one_hot`; `non_zero`; `band_part`; `reverse_sequence`; `shape`;
`sliding_windows`; logical `and`/`or`/`xor`; the recurrent cells `gru`/`lstm`/`rnn`; inverse and hyperbolic
trig; and the random-sampling ops other than the uniform generator. `DOCUMENTED` (paper ch. 4). Our M4 scan
agrees on the category (`acos asin atanh cosh sinh tan`, `argsort non_zero one_hot shape cumsum
reduce_argmax reduce_argmin reduce_prod`, `scatter*`, `gru lstm rnn`, `random_*`, `non_maximum_suppression`,
`band_part reverse_sequence sliding_windows mod`) — `MEASURED`, ours.

Family-gated rather than universal (`DOCUMENTED`, paper ch. 4 / Appendix A):

- **Texture-engine** ops (resize as a hardware sampler, crop-resize, resample, affine) — absent on M1, arrive
  on A14/M2.
- **Native `sin`/`cos`** — only from A15/M3; on M1/A14 they reject and decompose on the host.
- **Whole-tensor argmin/argmax on the IL route** — gated to A15, but reachable on M1 through the *bridge*
  route because the hardware feature byte is already set on A13. This is the cleanest example that an op's
  availability differs between Apple's two compile routes on the same silicon.
- **`gather`** — a software path valid only inside a narrow envelope (batch 1, depth 1, 3-element index
  channel); outside it the compiler aborts rather than falling back.

And the rule that makes all of this treacherous (paper ch. 4, "**Attested is not reachable**"): three-
dimensional convolution is *advertised by a hardware capability byte and recognized by the compiler frontend*
yet "fails backend lowering on every device mask"; on M1 the top-k, sort and dynamic-slice validators are
callable but the code generator rejects all three. A capability bit, a frontend acceptance, or a validator
pass is a claim about one layer; only compile-and-run confirms the op at the layer that executes it.
`DOCUMENTED`.

The community layer-level list (`neural-engine/docs/unsupported-layers.md`, `CLAIMED`, and it says so
itself: "incomplete and possibly wrong") names custom layers, RNN layers, gather, dilated convolutions,
broadcastable and "ND" layer types, certain broadcasting ops (`CxHxW` × `Cx1x1`), pooling with kernel > 13 or
stride > 2, and upsampling with scale > 2. Its actionable content is that most of these can be *rewritten*
into older layer types that do lower: `AddBroadcastableLayer → AddLayer`, `MultiplyBroadcastableLayer →
MultiplyLayer/ScaleLayer`, `ConcatND → Concat`, `LoadConstantND → LoadConstant`. That is a compile-stage
surgery pattern, and it is the ancestor of what Apple now says officially.

### 5.4 Silent fallback: the placement trap

The op lists above describe the *compiler's* verdict. The failure mode that costs people days is that the
compiler's verdict is not what runs. Two documented statements of that:

- `computeUnits = .all` "does not *guarantee* the model will run on the ANE, it just tells Core ML that you
  prefer to use the ANE if available" (`DOCUMENTED`, neural-engine `running-on-ane.md`, consistent with Apple's
  own docs). The planner "is opaque. A caller does not choose the device and is not told which device ran the
  work." (decompiled-paper).
- Placement is a property of **how a computation is expressed, not what it computes** — the headline result of
  arXiv:2608.22110: "a fused RMSNorm is fully ANE-eligible while its arithmetically identical decomposition is
  CPU-only", and a 25.85M-parameter conv-heavy fp16 model is assigned *entirely to the CPU* (zero bytes
  through the engine, confirmed by the ANE's memory-controller byte counters) while the same graph in int8 or
  2-bit returns to ~83% residency and runs 1.8–2.2x faster. `DOCUMENTED` (abstract); the counter-reading
  method is that paper's own MEASURED work.
- And on the Core AI side, the same shape of problem: a graph can "compile but run on CPU", and the documented
  fix is an explicit `--preferred-compute neural-engine` (`coreai-model-zoo/knowledge/compute-units-and-authoring.md`,
  citing Apple's own `common_issues.md:109-112`). `DOCUMENTED`.

`ane-probe`'s `MLComputePlan` query is a *static* prediction ("compute plan results reflect the compiler's
static analysis; actual runtime behavior may vary"), so it tells you eligibility, not placement.
`DOCUMENTED` (ane-probe README). The only trustworthy check is the one Chapter 4 of the paper prescribes:
compile a single-op graph and run it, or watch ANE counters/power while the real model runs.

---

## 6. How to run the compile chain ourselves (summary)

1. **Author ANE-shaped**: `(B, C, 1, S)` layout, sequence on the last (unpacked, 64-byte-aligned) axis, every
   `Linear` as a 1x1 `Conv2d`, no stray fp32 literals, per-head attention rather than fused SDPA, rank ≤ 5.
   `DOCUMENTED` (Apple guidance + `coreai-model-zoo` rules).
2. **Convert**: `coremltools.convert(..., convert_to="mlprogram")` for Core ML, or `coreai-torch` +
   `coreai-opt` + `save_asset()` for Core AI. Inspect `model.mil` (text) or `stats.json` (op census) to see
   what the compiler was actually handed.
3. **Compile**: let Core ML specialize at load (produces `<ARCH>.bundle/<proc>/main_ane/model.hwx` +
   `<ARCH>.e5`), or AOT with `xcrun coreai-build compile --preferred-compute neural-engine --architecture <arch>`.
   Architecture names track the **device identifier**, not the marketing name (`h16g` for `Mac16,x`), and
   `coreai-build` exits 0 for *any* requested arch — only a device load validates the choice.
4. **Count what you got**: `find <.aimodelc> -name '*ANE_region_*.mlir.bc' | wc -l` (regions) and the
   `warm/cold` load split. Fewer regions is a load-time win, not a steady-state one.
5. **Verify placement, don't assume it**: compile-and-run a single-op graph for eligibility, and read ANE
   counters/power for the real model. Neither `preferred` nor a capability byte nor a validator pass is
   evidence that the op ran on the engine.

---

## Sources

External:

- https://arxiv.org/abs/2606.22283 — S. H. Bryngelson, *Apple Neural Engine: Architecture, Programming, and
  Performance* (2026-06-21). Abstract page + full HTML `https://arxiv.org/html/2606.22283v1` (read in full
  for chs. 4, 6, 20–23, 34 and Appendix A). Claims in that paper are marked measured / decompile-derived /
  predicted; this file labels them accordingly.
- https://arxiv.org/abs/2608.22110 — S. M. A, *What actually runs: a measurement study of language model
  placement and decode speed on the Apple Neural Engine* (2026-08-22). Abstract only; the full-text HTML URL
  returned a stub (7.9 KB), so only abstract-level claims are used.
- https://eiln.github.io/posts/ane-dma.html — Eileen Yoon, *Getting 50 GB/s Back Out of the ANE* (2026-08-10).
  Task-descriptor offsets, core-register layout, KMem size, the 1 MiB/core erratum.
- https://machinelearning.apple.com/research/apple-neural-engine — Apple, *Deploying Transformers on the
  Apple Neural Engine* (2022-06-06). This URL redirects to
  https://machinelearning.apple.com/research/neural-engine-transformers; the content served is that article.
- https://developer.apple.com/documentation/coreml — Apple, Core ML framework documentation.
- https://github.com/eiln/ane — referenced by the paper as the reverse-engineered Linux driver + `anecc`
  compiler (not fetched in this pass).

Local:

- `/Volumes/data/local_ai_stack/repos/neural-engine/docs/` — `unsupported-layers.md`, `running-on-ane.md`,
  `model-surgery.md`, `is-model-using-ane.md`, `16-bit.md`, `other.md`, `internals.md`, `programming-ane.md`,
  `reverse-engineering.md`.
- `/Volumes/data/local_ai_stack/repos/ane-probe/README.md` and
  `/Volumes/data/local_ai_stack/results/EXP-001-ane-op-map/` (`README.md`, `ane_support_results.csv`).
- `/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/` — `aot-and-specialization.md`,
  `coreai-overview.md`, `ane-silicon-reference.md`, `compute-units-and-authoring.md`.
- `/Volumes/data/local_ai_stack/repos/ml-ane-transformers/README.md`.
- `/Volumes/data/local_ai_stack/results/RESEARCH-SWEEP.md`.
- `/Volumes/data/local_ai_stack/work/exports/von-retest/` and `.../laya-proto/` — the `.aimodel` and
  `.aimodelc` bundles we inspected byte by byte.
- `/Volumes/data/local_ai_stack/.venv/lib/python3.13/site-packages/coremltools/modelrunner/ModelRunner/add_model.mlmodelc`
  (and the copy under `.venv/`).
- `/System/Library/AssetsV2/com_apple_MobileAsset_UAF_Siri_Understanding/purpose_auto/8f24c5d784dbd320bb3ae748e2d7d871fb61616e.asset/.AssetData/VAD.mlmodelc`
  and the sibling `encoder.mlmodelc`.
- `/System/Library/PrivateFrameworks/VideoProcessing.framework/Versions/A/Resources/cnn_frame_enhancer_96p.H17.espresso.hwx`
  (and the H13–H17 variants in the same directory).

## Records

```jsonl
{"id":"FORMAT-001","claim":"A converted Core ML model is a directory bundle (.mlmodelc) whose compiled ANE program is not inside it; the engine program is produced by on-device specialization and cached in a nested model.specialization.bundle.","kind":"fact","confidence":"measured","source":"/System/Library/AssetsV2/com_apple_MobileAsset_UAF_Siri_Understanding/purpose_auto/8f24c5d784dbd320bb3ae748e2d7d871fb61616e.asset/.AssetData/VAD.mlmodelc","source_type":"our-own","retrieved":"2026-09-23","topic":["compile","artifact","mlmodelc"],"entities":["Core ML","mlmodelc","ANE"],"evidence":"VAD.mlmodelc contains only model.mil.config, weights/, and model.specialization.bundle/H16G.bundle/{H16G.e5, main/main_ane/model.hwx}","caveat":"inspected on macOS 27.0, M4","contested":false}
{"id":"FORMAT-002","claim":"A compiled Core ML ANE program is stored at model.specialization.bundle/<ARCH>.bundle/<procedure>/main_ane/model.hwx, where <ARCH> is an engine generation name such as H16G.","kind":"fact","confidence":"measured","source":"/System/Library/AssetsV2/com_apple_MobileAsset_UAF_Siri_Understanding/purpose_auto/8f24c5d784dbd320bb3ae748e2d7d871fb61616e.asset/.AssetData/VAD.mlmodelc","source_type":"our-own","retrieved":"2026-09-23","topic":["compile","artifact","hwx"],"entities":["Core ML","model.hwx","H16G"],"evidence":"directory listing on this machine","caveat":"observed layout on macOS 27; Apple does not document this path","contested":false}
{"id":"FORMAT-003","claim":"The ANE program file model.hwx is Mach-O-shaped with magic 0xbeefface, cputype 0x80 (an engine pseudo-architecture), and filetype 2 (executable), rather than the real 64-bit Mach-O magic 0xfeedfacf.","kind":"fact","confidence":"measured","source":"/System/Library/PrivateFrameworks/VideoProcessing.framework/Versions/A/Resources/cnn_frame_enhancer_96p.H17.espresso.hwx","source_type":"our-own","retrieved":"2026-09-23","topic":["program-format","hwx","mach-o"],"entities":["model.hwx","Mach-O"],"evidence":"header parse: magic=0xbeefface cputype=0x80 filetype=2; paper reports the same and notes patching the four magic bytes lets otool/rabin2 parse it","caveat":"we parsed two files locally; format decode credit arXiv:2606.22283 ch.23","contested":false}
{"id":"FORMAT-004","claim":"A model.hwx container is organised into __PAGEZERO, __FVMLIB, __TEXT and __KERN_0 segments, where the __FVMLIB segments have fileoff and filesize zero and exist only as virtual-memory declarations for the input/output apertures.","kind":"fact","confidence":"measured","source":"/System/Library/PrivateFrameworks/VideoProcessing.framework/Versions/A/Resources/cnn_frame_enhancer_96p.H17.espresso.hwx","source_type":"our-own","retrieved":"2026-09-23","topic":["program-format","hwx","segments"],"entities":["model.hwx","__FVMLIB","__KERN_0"],"evidence":"our Mach-O load-command parse on cnn_frame_enhancer_96p.H17.espresso.hwx showed 11 __FVMLIB windows with filesize 0 plus __TEXT (__text,__const) and __KERN_0 (__kern_0)","caveat":"interpretation of the zero-fileoff windows is from arXiv:2606.22283 ch.23","contested":false}
{"id":"FORMAT-005","claim":"The __TEXT section of a model.hwx holds the task-descriptor register-write stream and the __KERN_0 section holds the weight coefficients tiled for the streaming datapath.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["program-format","hwx","registers"],"entities":["model.hwx","task descriptor","__KERN_0"],"evidence":"Chapter 23: 'whose text section holds the task-descriptor register-write stream and whose __KERN_N sections hold the weight coefficients'","caveat":"decompile-derived claim from the paper, verified there on H13 samples, not re-decoded by us","contested":false}
{"id":"FORMAT-006","claim":"Inside a model.hwx container the convolution weight tiling stride is 0xC0 bytes and the matrix-multiply weight tiling stride is 0x40 bytes, and a weight-value edit leaves the program descriptor unchanged so weights are patchable in place.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["program-format","weights","tiling"],"entities":["model.hwx","weight tiling"],"evidence":"Chapter 23 tables 23.10 and 23.5.2; weight split into min(8, lanes) 64-byte-aligned tiles named K<sha256>_ne_<i>","caveat":"decoded from M1/H13 samples","contested":false,"split":"holdout"}
{"id":"FORMAT-007","claim":"A compiled ANE program contains 16 core base-address register words (TD+0x078 stepping by 4) and 16 core size words (TD+0x0b4 through TD+0x0f0).","kind":"fact","confidence":"measured","source":"https://eiln.github.io/posts/ane-dma.html","source_type":"primary","retrieved":"2026-09-23","topic":["registers","task-descriptor","cores"],"entities":["ANE","M3","task descriptor"],"evidence":"D=2044/2048/2052 register dumps listing core 1 base at TD+0x078 through core 15 base at TD+0x0b0 and sizes TD+0x0b4-0x0f0","caveat":"measured on an M3 Air; register offsets are generation-specific","contested":false}
{"id":"FORMAT-008","claim":"When the ANE splits a weight buffer across cores, each core receives an equal contiguous slice: at D=2048 each core's slice is 1 MiB and core k's base address is k times 1 MiB.","kind":"fact","confidence":"measured","source":"https://eiln.github.io/posts/ane-dma.html","source_type":"primary","retrieved":"2026-09-23","topic":["registers","partitioning","dma"],"entities":["ANE","M3"],"evidence":"TD+0x078 core1 base 0x00100000, TD+0x07c core2 base 0x00200000, TD+0x0b0 core15 base 0x00f00000 at D=2048","caveat":"M3 measurement; the register-level view of the same partition the compiler expresses as output-channel round-robin","contested":false}
{"id":"FORMAT-009","claim":"The ANE's resident kernel memory for weights is 64 KiB per core.","kind":"fact","confidence":"measured","source":"https://eiln.github.io/posts/ane-dma.html","source_type":"primary","retrieved":"2026-09-23","topic":["memory","kmem","weights"],"entities":["ANE","M3","KMem"],"evidence":"'Given that the resident \"L1\" KMem is 64 KiB per core'; independently, arXiv:2606.22283 ch.21 and its per-chip limit table give a 64 KB kernel-coefficient store for every family A13 through A16/M5","caveat":"two independent methods agree; measured on M3 and decompiled on M1","contested":false}
{"id":"FORMAT-010","claim":"The ANE on-chip operand working set is 2 MB on M1, exposed in the compiler as HAL field 0x1b8, and a layer whose largest single operand exceeds it is tiled and streamed from DRAM.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["memory","l2","working-set"],"entities":["ANE","M1"],"evidence":"Chapter 21: HAL[0x1b8] = 2 MB on M1, aliased MemCacheSize/L2Size; the comparison is on one tensor, not the sum of operands","caveat":"M1 value; M5 raises the bound to about 4.72 MB","contested":false}
{"id":"FORMAT-011","claim":"The measured throughput threshold for the ANE on-chip working set occurs at 2.28 to 2.34 MB rather than exactly 2 MB, because the tiler holds about 0.3 MB of double-buffer and alignment margin.","kind":"measurement","confidence":"measured","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["memory","l2","working-set","measurement"],"entities":["ANE","M1"],"evidence":"batched matmul sweep: 1.25-2.25 MB plateau 700-850 GFLOP/s, 2.28 MB 992, 2.34 MB 1038 (a 185 GFLOP/s step for a 0.03 MB change)","caveat":"M1 measurement; throughput rises above the threshold because tiled weights double-buffer","contested":false}
{"id":"FORMAT-012","claim":"The ANE's on-chip pool is interleaved across 64 banks at a 16-byte granule, with bank index computed as ((address / 16) mod 64).","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["memory","banks","l2"],"entities":["ANE","M1"],"evidence":"Chapter 21: bank count field 0x1c8 = 64, interleave granule field 0x1c0 = 16 bytes; the bank-conflict cost vector has exactly 64 float entries","caveat":"M1/H13 values; the pool is a compiler-managed scratchpad rather than a demand-filled cache","contested":false}
{"id":"FORMAT-013","claim":"The ANE compiler assigns output channels to cores by a strided round-robin, so on a part with N cores output channel c is assigned to core (c mod N).","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["execution-model","cores","partitioning"],"entities":["ANE","ZinMirNECoreAssignment"],"evidence":"Chapter 20.6 and listing 33; N = HAL[0x238] = 4 on M1","caveat":"decompile-derived; the core count N is the compiler's per-die field, which differs from Apple's published core count","contested":false}
{"id":"FORMAT-014","claim":"The ANE's active core count for a task is shape-driven rather than user-selectable: it is derived from the output-channel count and the output-channel-group size, rounded up to a power of two, and written into the task descriptor's 3-bit ActiveNE field.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["execution-model","cores","partitioning"],"entities":["ANE","ActiveNE"],"evidence":"Chapter 20.6 listing 33: cores_needed = min(num_nes, next_pow2(ceil(c_out / ocg)))","caveat":"decompile-derived from M1 compiler","contested":false}
{"id":"FORMAT-015","claim":"The publicly stated ANE core count of 16 differs from the compiler's per-die core-count field, which decodes to 4 on the M1 base part and 8 on g-suffixed parts.","kind":"open-question","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["execution-model","cores","contested"],"entities":["ANE","M1","HAL 0x238"],"evidence":"Chapter 20.1 states the decoded four counts physical compute sets while 'the 16-core count the I/O registry also reports is a different quantity'; the power rail shows ~10 mW per added core over an ~800 mW floor matching four power-gated compute sets","caveat":"the two figures may describe different layers (hardware partitions vs power-gated compute sets vs compiler-visible engines) and no source reconciles them","contested":true}
{"id":"FORMAT-016","claim":"The ANE on the M3 contains 16 parallel hardware partitions, each holding its own slice of a weight buffer, and latency is constant whether 1 or 16 of them are active.","kind":"measurement","confidence":"measured","source":"https://eiln.github.io/posts/ane-dma.html","source_type":"primary","retrieved":"2026-09-23","topic":["execution-model","cores","contested"],"entities":["ANE","M3"],"evidence":"'ANE has 16 cores in parallel'; active-core sweep from 1 to 16 showed constant latency for both D=2016 and D=2048","caveat":"M3 measurement; conflicts in vocabulary with the compiler's 4-core per-die field on M1 and with Apple's marketing count","contested":true,"split":"holdout"}
{"id":"FORMAT-017","claim":"A matrix multiply or fully-connected layer whose right-hand weight fits the on-chip working set is rewritten by the ANE compiler into a resident convolution by the pass ReplaceMatmulWithConv.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","matmul","conv1x1"],"entities":["ANE","ReplaceMatmulWithConv","anec.matmul"],"evidence":"Chapter 22.3 fusion-rule table and Chapter 21 listing 34 (ZinMirMatMul::LowerNEMatMulToNEConv rejects a resident RHS above HAL[0x1b8])","caveat":"decompile-derived; above the working-set bound the op stays a tiled matrix multiply","contested":false}
{"id":"FORMAT-018","claim":"Apple instructs developers to replace nn.Linear layers with nn.Conv2d layers when targeting the ANE, mapping the sequence axis to the last (width) axis of a (B, C, 1, S) tensor.","kind":"procedure","confidence":"documented","source":"https://machinelearning.apple.com/research/apple-neural-engine","source_type":"primary","retrieved":"2026-09-23","topic":["authoring","layout","conv1x1"],"entities":["Core ML","ANE","ml-ane-transformers"],"evidence":"'we swap all nn.Linear layers with nn.Conv2d layers'; the article also states the (B,C,1,S) format is the most conducive for the ANE and that the last axis must be contiguous and aligned to 64 bytes","caveat":"URL redirects to /research/neural-engine-transformers; guidance is stated for A14/M1 and later","contested":false}
{"id":"FORMAT-019","claim":"The ANE buffer convention requires the last tensor axis to be contiguous and aligned to 64 bytes, and a singleton last axis is padded to 64 bytes, costing 32 times the memory in fp16 and 64 times in 8-bit precision.","kind":"gotcha","confidence":"documented","source":"https://machinelearning.apple.com/research/apple-neural-engine","source_type":"primary","retrieved":"2026-09-23","topic":["layout","alignment","gotcha"],"entities":["ANE","Core ML"],"evidence":"Article Principle 1: 'the last axis of an ANE buffer is not packed; it must be contiguous and aligned to 64 bytes', with the 32x/64x padding cost example","caveat":"Apple's own guidance, not reproduced by us on hardware","contested":false}
{"id":"FORMAT-020","claim":"The ANE compiler runs four phases: graph fusion to one fused compute operation, legalization to the hardware envelope, schedule and task-descriptor partitioning, and memory/DMA optimization.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","pipeline"],"entities":["ANECompiler","ZinIr","ZinMir"],"evidence":"Chapter 22.1 table 22.1 listing representative passes per phase","caveat":"decompile-derived from the M1 compiler","contested":false}
{"id":"FORMAT-021","claim":"Graph fusion on the ANE happens inside ANECompiler's ZinIr/ZinMir layer-graph stage, not in the MIL the host hands over.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","fusion","mil"],"entities":["MIL","ANECompiler","ZinIr"],"evidence":"Chapter 22.3: 'a biased, activated convolution arrives as three separate operations, conv then add(x=conv, y=bias_const) then relu, and the collapse into one engine layer happens entirely inside ANECompiler's ZinIr/ZinMir layer-graph stage'","caveat":"decompile-derived","contested":false}
{"id":"FORMAT-022","claim":"A convolution, matrix multiply, pool, or elementwise operation on the ANE can absorb a seven-slot epilogue chain in fixed order: texture remap, broadcast, pre-GOC activation, gain-offset affine, post-GOC activation, output transpose, and output requantization.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","fusion","epilogue"],"entities":["ZinNEBypassLayer","GOC"],"evidence":"Chapter 22.3 listing 40 gives the ZinNEBypassLayer constructor whose argument order fixes the seven slots","caveat":"decompile-derived","contested":false}
{"id":"FORMAT-023","claim":"A two-live-input elementwise operation on the ANE does not fuse into a gain-offset control and remains a real anec.add engine layer, because the gain-offset unit is an affine of one tensor.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","fusion","barrier"],"entities":["anec.add","GOC"],"evidence":"Chapter 22.3: guard 'Must have 2 inputs when convert EW to GOC'; add(conv_a, conv_b) fails the one-constant guard and separates the two convolutions","caveat":"decompile-derived","contested":false}
{"id":"FORMAT-024","claim":"Scaled-dot-product attention is a hard segment cut between ANE programs, so it acts as a compilation boundary rather than a fusable layer.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","fusion","attention"],"entities":["SDPA","ANECompiler"],"evidence":"Chapter 22.3 table 22.3 lists scaled-dot-product attention as 'a hard segment cut between programs'","caveat":"decompile-derived; the fused SDPA layer itself is native from the M1 onward, so this is about the compiler's segmentation","contested":false,"split":"holdout"}
{"id":"FORMAT-025","claim":"The ANE compiler partitions a graph into on-engine task-descriptor partitions by a memory test rather than an operation count: it closes the current partition when peak L2 pressure would exceed a fraction of the on-chip static-memory ceiling.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","partitioning","memory"],"entities":["ANECompiler","L2"],"evidence":"Chapter 22.1: partition closes when peak L2 pressure > HAL[0x1b8] x f where f is a margin fraction below one","caveat":"decompile-derived; the ceiling field is 2 MB on M1","contested":false}
{"id":"FORMAT-026","claim":"The ANE compiler marks a single-fanout producer followed by a same-engine consumer with matching tile geometry as 'chainable' (allocation type 2), keeping the producer's output on chip and supplying the consumer in place instead of round-tripping through DRAM.","kind":"definition","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","chaining","l2"],"entities":["ANECompiler","L2 chaining"],"evidence":"Chapter 22.1 table 22.2 allocation types 0-8, with type 2 described as the double-buffer state","caveat":"decompile-derived; chaining is a structural pattern, not a size threshold","contested":false}
{"id":"FORMAT-027","claim":"Two ANE operations can co-issue only when one is a multiply-accumulate operation and the other is a planar-engine operation, and chaining and co-issue are mutually exclusive.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","scheduling","co-issue"],"entities":["ANECompiler","planar engine"],"evidence":"Chapter 22.1 Phase 3 co-issue discovery rules; the selected pattern is softmax on the planar engine co-issued with a value matrix multiply on the MAC array","caveat":"decompile-derived","contested":false}
{"id":"FORMAT-028","claim":"Compilation to the ANE program format is performed out of process by the sandboxed XPC service com.apple.ANECompilerService, whose single entry point is compileModelAt:csIdentity:sandboxExtension:options:tempDirectory:...:withReply:.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","service","xpc"],"entities":["ANECompilerService","Espresso"],"evidence":"Chapter 6 decompile of the compiler service interface","caveat":"decompile-derived; on macOS the service is shared, and the paper notes a failed compile restarts it","contested":false}
{"id":"FORMAT-029","claim":"The ANE runtime writes compiled programs to a content-addressed cache on disk keyed by network structure, weights, source URL, options and platform, rather than by source filename.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","cache","artifact"],"entities":["ANECompiler","cacheURLIdentifier"],"evidence":"Chapter 5: cacheURLIdentifier assembled from a per-segment key over each segment's network structure and weight blobs combined with the resolved source URL, options dictionary, and platform","caveat":"decompile-derived","contested":false}
{"id":"FORMAT-030","claim":"The five steps of the ANE direct route are: build a network description, compile it to the engine's program format, load the compiled program, bind operand buffers, and dispatch.","kind":"procedure","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","direct-route","procedure"],"entities":["Espresso","e5rt"],"evidence":"Chapter 6.1 with the e5rt_* call sequence in listing 12","caveat":"private, undocumented, version-fragile route; compile and load are once per network, bind and dispatch are the hot loop","contested":false}
{"id":"FORMAT-031","claim":"Reaching the ANE by the direct route requires compiling a network description (a netplist) with the Espresso runtime's e5rt_* C dispatch layer rather than going through Core ML.","kind":"procedure","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","direct-route"],"entities":["e5rt_e5_compiler_compile","netplist"],"evidence":"Chapter 6 listing 12: e5rt_e5_compiler_create_with_config, e5rt_e5_compiler_compile, e5rt_program_library_retain_program_function, e5rt_execution_stream_encode_operation","caveat":"undocumented, unsupported, version-fragile, not App-Store-safe","contested":false}
{"id":"FORMAT-032","claim":"The MIL (Model Intermediate Language) is the host-side intermediate representation coremltools converts a source model into before the ANE compiler sees it.","kind":"definition","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/ane-probe/README.md","source_type":"secondary","retrieved":"2026-09-23","topic":["compile","mil","pipeline"],"entities":["MIL","coremltools"],"evidence":"ane-probe builds tiny single-op MIL programs and converts them with coremltools.convert() before querying MLComputePlan","caveat":"MIL is Apple's own IR but the ANE lowering step below it is undocumented","contested":false}
{"id":"FORMAT-033","claim":"A converted Core ML program on disk contains a text MIL program in model.mil beginning with 'program(1.0)' and a buildInfo header naming the coremlc and coremltools versions.","kind":"fact","confidence":"measured","source":"/Volumes/data/local_ai_stack/.venv/lib/python3.13/site-packages/coremltools/modelrunner/ModelRunner/add_model.mlmodelc/model.mil","source_type":"our-own","retrieved":"2026-09-23","topic":["artifact","mil","mlmodelc"],"entities":["model.mil","coremltools"],"evidence":"file begins 'program(1.0)' with buildInfo coremlc-component-MIL 3402.3.2, coremlc-version 3402.4.1, coremltools-version 8.1","caveat":"a coremltools test fixture, not a production model","contested":false}
{"id":"FORMAT-034","claim":"A compiled Core AI portable model (.aimodel) is a directory bundle of metadata.json, main.mlirb and main.hash, with no device-specific executable until specialization.","kind":"fact","confidence":"measured","source":"/Volumes/data/local_ai_stack/work/exports/von-retest/von-1.0_v1_float16_s256_ane.aimodel","source_type":"our-own","retrieved":"2026-09-23","topic":["artifact","aimodel","coreai"],"entities":["Core AI","aimodel","mlirb"],"evidence":"metadata.json (license, author, description, assetVersion 2.0, producer coreai-core 1.0.0b2, creationDate) plus main.mlirb 792,214,837 B and main.hash 32 B","caveat":"produced with a Core AI beta toolchain on macOS 27","contested":false}
{"id":"FORMAT-035","claim":"A Core AI main.mlirb file is serialized MLIR bytecode: its first bytes are the MLIR bytecode magic ML\\xefR followed by the string MLIR22.0.0git.","kind":"fact","confidence":"measured","source":"/Volumes/data/local_ai_stack/work/exports/von-retest/von-1.0_v1_float16_s256_ane.aimodel/main.mlirb","source_type":"our-own","retrieved":"2026-09-23","topic":["artifact","mlirb","mlir"],"entities":["Core AI","MLIR"],"evidence":"hex dump starts 4d4c ef52 0d4d 4c49 5232 322e 302e 3067 6974 = ML\\xefR MLIR22.0.0git","caveat":"observed on one exported model; MLIR bytecode version may change with toolchain","contested":false,"split":"holdout"}
{"id":"FORMAT-036","claim":"A Core AI .aimodel bundle inlines its weights into main.mlirb, so the file size is dominated by fp16 parameter bytes.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/work/exports/von-retest/von-1.0_v1_float16_s256_ane.aimodel/main.mlirb","source_type":"our-own","retrieved":"2026-09-23","topic":["artifact","weights","aimodel"],"entities":["Von-1.0","main.mlirb"],"evidence":"main.mlirb is 792,214,837 bytes and the companion stats.json reports Float16 storage count 395,899,912, which is 791,799,824 bytes","caveat":"one model (Von-1.0 ModernBERT-Large re-authored for the ANE at S=256)","contested":false}
{"id":"FORMAT-037","claim":"A Core AI AOT compile with --preferred-compute neural-engine still emits an MPSGraph delegate, and the ANE portion of the graph appears inside it as an ANE region of MLIR bytecode with its own weights file.","kind":"fact","confidence":"measured","source":"/Volumes/data/local_ai_stack/work/exports/von-retest/aot/von-1.0_v1_float16_s256_ane.h16g.aimodelc/main-h16g-delegates","source_type":"our-own","retrieved":"2026-09-23","topic":["artifact","aimodelc","delegate"],"entities":["Core AI","MPSGraph","ANE region"],"evidence":"main-h16g-delegates/MPSGraph/mpsExecutable.mpsgraphpackage contains specialized_model_1.mpsgraph, original_model_0.mpsgraph, resources.bin (791,809,168 B) and binary_0.llir.bundle/..._ANE_region_0_0.bc/{h16g/..._ANE_region_0_0.mlir.bc, ..._0_ANE_region_0_0.bc.weights}","caveat":"one model on a Core AI beta toolchain; whether the region is later lowered to the same HWX form Core ML produces is unverified","contested":false}
{"id":"FORMAT-038","claim":"A .aimodelc compiled package contains one main-<arch>.mlirb plus a per-architecture ANE region directory and its own metadata.json, stats.json and main.hash.","kind":"fact","confidence":"measured","source":"/Volumes/data/local_ai_stack/work/exports/von-retest/aot/von-1.0_v1_float16_s256_ane.h16g.aimodelc","source_type":"our-own","retrieved":"2026-09-23","topic":["artifact","aimodelc"],"entities":["coreai-build","aimodelc"],"evidence":"bundle holds metadata.json (producer coreai-build-3600.83.1, sourceHash, assetVersion 2.0), stats.json, main-h16g.mlirb (1,628 B), main.hash and main-h16g-delegates/","caveat":"observed on macOS 27 with a Core AI beta toolchain","contested":false}
{"id":"FORMAT-039","claim":"The number of ANE regions in a compiled .aimodelc is directly countable with 'find <bundle> -name *ANE_region_*.mlir.bc | wc -l'.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/compute-units-and-authoring.md","source_type":"our-own","retrieved":"2026-09-23","topic":["artifact","aimodelc","measurement"],"entities":["Core AI","ANE region"],"evidence":"the note prescribes exactly this command and we see one ANE_region directory in our von .aimodelc","caveat":"the region count is a load-time and segmentation property, not a steady-state speed property","contested":false}
{"id":"FORMAT-040","claim":"Re-authoring a 600M-parameter Parakeet FastConformer encoder for the ANE halved its ANE region count from 49 to 25, cutting cold load from 65.7 s to 11.9 s and warm load from 2.2 s to 0.59 s without changing steady-state speed.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/compute-units-and-authoring.md","source_type":"our-own","retrieved":"2026-09-23","topic":["compile","load-time","ane-regions"],"entities":["Parakeet","Core AI","iPhone 17 Pro"],"evidence":"iPhone 17 Pro, iOS 27, AOT h18p, L=2885 fp16, warm median of 20 passes; both ANE routes lose to the GPU one by about 1.7x in throughput","caveat":"measured on a phone, not on this Mac; a project measurement rather than a third-party independent one","contested":false}
{"id":"FORMAT-041","claim":"The ANE dispatch descriptor is a FlatBuffer whose root table has four fields (symbol_names, build_info, sections, format_version) and whose format_version was observed to be 4.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["descriptor","flatbuffer","e5"],"entities":["E5Program","dispatch descriptor"],"evidence":"Chapter 23.2 table 23.2, schema recovered from the E5Serializer symbol family and validated against a real H13C descriptor of 3816 bytes","caveat":"decompile-derived; the runtime strips the binary schema so this was recovered from symbol names","contested":false}
{"id":"FORMAT-042","claim":"The vtable bytes 0c00 1400 0400 0800 appear at the start of a shipping ANE dispatch descriptor (.e5) file as well as in the decompiled FlatBuffer schema.","kind":"fact","confidence":"measured","source":"/System/Library/AssetsV2/com_apple_MobileAsset_UAF_Siri_Understanding/purpose_auto/8f24c5d784dbd320bb3ae748e2d7d871fb61616e.asset/.AssetData/VAD.mlmodelc/model.specialization.bundle/H16G.bundle/H16G.e5","source_type":"our-own","retrieved":"2026-09-23","topic":["descriptor","e5","flatbuffer"],"entities":["H16G.e5","dispatch descriptor"],"evidence":"first 16 bytes of the 14,032-byte file are 1400 0000 0000 0000 0c00 1400 0400 0800; arXiv:2606.22283 ch.23 gives the same vtable for the dispatch descriptor","caveat":"byte-level match on one shipping file; the paper's full decode of the tables is decompile-derived","contested":false}
{"id":"FORMAT-043","claim":"The canonical ANE dispatch descriptor shape for a single fused graph is Cast then AneInference then Cast, with the whole fused graph expressed as one inference operation.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["descriptor","fusion","structure"],"entities":["E5Program","AneInference"],"evidence":"Chapter 23.2; the descriptor is depth-invariant so a one-operation graph and a six-operation fused graph reduce to the same-sized inference operation","caveat":"decompile-derived","contested":false,"split":"holdout"}
{"id":"FORMAT-044","claim":"The ANE dispatch descriptor tracks dispatch count rather than operation count: a bridge operation that cuts the graph into three segments produces three inference operations and a larger descriptor.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["descriptor","segmentation"],"entities":["E5Program","bridge operation"],"evidence":"Chapter 23.2","caveat":"decompile-derived","contested":false}
{"id":"FORMAT-045","claim":"The ANE dispatch descriptor's operand layout record is a TensorDescriptor holding dim[4], stride[4], width, height, channels, batch_number, sequence_length, their strides, and an int32 storage_type code.","kind":"definition","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["descriptor","tensor","layout"],"entities":["TensorDescriptor"],"evidence":"Chapter 23.2 listing 42, recovered verbatim from a runtime type-encoding string","caveat":"the two leading pointers in the struct are runtime-only and not serialized","contested":false}
{"id":"FORMAT-046","claim":"The ANE serialization element-type space is a closed set of eleven codes: int4 0, uint8 1, int8 2, float16 3, float32 4, int16 5, uint16 6, int32 7, uint32 8, int64 9, uint64 10.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["descriptor","dtypes"],"entities":["element type catalog"],"evidence":"Chapter 23.6 table 23.12","caveat":"the container's symbol-table hardware catalog is wider (24 entries) because it also holds fp8 and palettized index types","contested":false}
{"id":"FORMAT-047","claim":"The ANE hardware task descriptor on the M1 is the versioned struct ZinAneTdHw_v10, a flat register image organised into seven register groups that the compiler fills field by field and serializes into address-value pairs.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["task-descriptor","registers","versioning"],"entities":["ZinAneTdHw_v10","task descriptor"],"evidence":"Chapters 20.8 and 23.3, tables 20.7 and 23.4","caveat":"decompile-derived; 14 versioned descriptor structs exist and byte offsets move between versions","contested":false}
{"id":"FORMAT-048","claim":"The M1 task descriptor's seven register groups are kernel-and-common at +0x2c, dimensions at +0xfc, tile DMA at +0x150, elementwise/planar at +0x26c, L2-and-texture at +0x2ec, kernel-format-and-op-mode at +0x32c, and L2-result at +0x360.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["task-descriptor","registers"],"entities":["ZinAneTdHw_v10"],"evidence":"Chapter 23.3 table 23.4 with register counts 34/19/69/30/14/11/21 and register bases 0x5500/-/0x4d00/0x4100/0x4500/0x4900/0x5100","caveat":"M1 v10 layout only; other generations use different versions with moved offsets","contested":false}
{"id":"FORMAT-049","claim":"The M1 ANE task descriptor does not write buffer base addresses into the compiled image; it leaves them as named relocation slots keyed by register address and the loader patches device addresses in at load.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["task-descriptor","relocation","loading"],"entities":["relocation table"],"evidence":"Chapter 23.3, v10 relocation map: 0x1344 input tile read, 0x134a second operand, 0x1442 output tile write, 0x1554 bias, 0x1558 post-scale, 0x155c palette lookup, 0x1560 activation lookup","caveat":"decompile-derived from M1","contested":false}
{"id":"FORMAT-050","claim":"A fused ANE convolution emits four independent kernel-coefficient streams (bias, post-scale, palette lookup, activation lookup), each with its own relocation slot, so batch-norm and activation folding do not become separate operations.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["task-descriptor","weights","fusion"],"entities":["ANE","kernel streams"],"evidence":"Chapters 20.8 and 23.3 tables 20.8 and 23.5; the activation lookup is a 33-segment piecewise-linear table","caveat":"decompile-derived","contested":false}
{"id":"FORMAT-051","claim":"The ANE task descriptor encodes spatial dimensions as 15-bit fields (mask 0x07fff) and channel dimensions as 17-bit fields (mask 0x1ffff, up to 131071).","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["task-descriptor","limits","registers"],"entities":["Win","Cin","Cout"],"evidence":"Chapter 23.3 listing 43: Win @0x0f4 mask 0x07fff, Hin @0x0f6 mask 0x07fff, Cin @0x100 mask 0x1ffff, Cout @0x104 mask 0x1ffff, OCGSize @0x118 mask 0x07, numGroups @0x11c mask 0x1fff","caveat":"M1 v10 decode","contested":false,"split":"holdout"}
{"id":"FORMAT-052","claim":"Each ANE direct-memory-access stride is a 26-bit signed field located at bit 6 of its register word and is range-checked against a per-chip bound table.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["task-descriptor","dma","strides"],"entities":["ANE","DMA"],"evidence":"Chapter 23.3","caveat":"decompile-derived from M1","contested":false}
{"id":"FORMAT-053","claim":"The ANE task-descriptor serializer is sparse: a register reaches the compiled stream only when its value differs from the architectural default, and each surviving record is a fixed 44 bytes.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["task-descriptor","serialization"],"entities":["ZinAneTd","register stream"],"evidence":"Chapter 23.3: a 64-to-64 identity linear layer yields only six to eight records; each is count marker, register address, and one or two device addresses","caveat":"decompile-derived","contested":false}
{"id":"FORMAT-054","claim":"The M1 ANE task descriptor omits the compute-cache direct-memory-access engine entirely, so resident in-place state cannot be expressed natively on that architecture and falls back to a shared buffer.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["task-descriptor","state","m1"],"entities":["M1","compute cache DMA"],"evidence":"Chapters 20.8 and 23.3: every setter for on-chip atomic, counter and wait-event primitives asserts unsupported on this architecture","caveat":"M1-specific architectural omission","contested":false}
{"id":"FORMAT-055","claim":"Codegen opcode words in a live M1 ANE task-descriptor stream decode as convolution 0x5042a063, reduce-mean 0x5000a021 and matrix multiply 0x5000b021.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["opcodes","task-descriptor"],"entities":["ZinAneTd","opcode"],"evidence":"Chapter 23.4 table 23.8; high half-word is shared across operations and the low 16 bits distinguish the op","caveat":"version-7 H13 codegen opcodes; the full operation identity is also in lookup-table and configuration words","contested":false}
{"id":"FORMAT-056","claim":"ANE task-descriptor records are chained by a next-record pointer at offset +0x1c and terminated by a null.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["task-descriptor","structure"],"entities":["ZinAneTd"],"evidence":"Chapter 23.5.1: three ZinAneTd records linked at 0x000 to 0x300 to 0x500 to terminator","caveat":"decoded from an M1 sample","contested":false}
{"id":"FORMAT-057","claim":"The ANE descriptor's operation-class enumeration has 79 members, including Conv 1, Pooling 2, Concat 3, ElementWise 4, ScaledElementWise 5, Neuron 6, GOC 8, MatrixMultiplication 18, Reduction 20, Softmax 24, Linear 60, NEConv 68, NEMatMul 69, NEPool 70, SDPA 77 and AllReduce 78.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["opcodes","descriptor","operations"],"entities":["operation mode enumeration"],"evidence":"Chapter 23.6 table 23.13","caveat":"decompile-derived; the full 79-member set and the 126-member micro-operation opcode space are in the paper's Appendix C","contested":false}
{"id":"FORMAT-058","claim":"There is no transposed-convolution operation class on the ANE; a transposed convolution lowers to a convolution, cross-correlation, or kernel rasterizer instead.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["operations","opcodes","deconvolution"],"entities":["transposed convolution"],"evidence":"Chapter 23.6 following table 23.13","caveat":"decompile-derived","contested":false}
{"id":"FORMAT-059","claim":"The ANE can compile for 28 architecture targets, and the suffix letter selects the core count within a generation: base 4 cores, g 8, s 16, c 32, d 64.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["cross-silicon","targets","cores"],"entities":["H13","H16g","H17s","H17d"],"evidence":"Chapter 34.1 table 34.1, core count decoded from HAL offset 0x238","caveat":"these are the compiler's per-die core fields, which the paper distinguishes from Apple's published core counts","contested":false}
{"id":"FORMAT-060","claim":"The M(n) to H(n+12) relation maps Mac generations to compiler targets: M1 is h13, M2 h14, M3 h15, M4 h16, M5 h17.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["cross-silicon","targets"],"entities":["M1","M4","M5","h16","h17"],"evidence":"Chapter 34.3 table 34.3 map from system-on-chip to runtime architecture and compiler target; anchored live on an M1 Max (h13g) and measured on an M5 Pro (h17s)","caveat":"middle steps rest on the anchored monotone board-type sequence","contested":false}
{"id":"FORMAT-061","claim":"The runtime architecture string (h16 for a base part, h16g for a Pro/Max/Ultra part) is coarser than the compiler target name (H16, H16g, H16s, H16c), and the two must be treated as separate identifiers.","kind":"gotcha","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["cross-silicon","naming","gotcha"],"entities":["h16g","H16g"],"evidence":"Chapter 34.4","caveat":"desktop platform emits only the h1N and h1Ng forms","contested":false}
{"id":"FORMAT-062","claim":"A model on this machine was AOT-compiled into a bundle named <model>.h16g.aimodelc, while the machine it was compiled on is an M4 base part (T8132).","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/work/exports/von-retest/aot/von-1.0_v1_float16_s256_ane.h16g.aimodelc","source_type":"our-own","retrieved":"2026-09-23","topic":["artifact","aimodelc","arch"],"entities":["h16g","M4"],"evidence":"directory name and internal ANE region directory h16g/; the workstation reports T8132 (M4 base)","caveat":"we did not verify that this artifact loads on this machine; coreai-build exits 0 for any requested architecture, so the arch choice is only validated by a device load","contested":false}
{"id":"FORMAT-063","claim":"Apple's Core AI specialization performs most of its latency in a core set of compilation steps that segment, plan and optimize compute, and its executable artifacts are tied to the device and OS version.","kind":"fact","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/aot-and-specialization.md","source_type":"secondary","retrieved":"2026-09-23","topic":["compile","coreai","specialization"],"entities":["Core AI","AIModelCache","SpecializationOptions"],"evidence":"WWDC 324 and 326 quoted verbatim in the note; 'This process can take a significant amount of time for very large models'","caveat":"distilled by our own project from WWDC transcripts, not read from Apple documentation directly","contested":false}
{"id":"FORMAT-064","claim":"The ANE compiler exposes 187 intermediate-language operations, of which about 108 are native on the M1, about 9 need M2 or later, 4 need M3 or later, 37 are rejected on every family, and about 24 are compiler-internal with no observed standalone code generation.","kind":"measurement","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["operations","coverage"],"entities":["MIL","M1","M5"],"evidence":"Appendix A introduction; every operation marked native was compiled and run on the M1","caveat":"M1, M2 and M5 columns are measured on silicon; M3 and the M4 half of the M4/M5 column are decompile-derived predictions","contested":false}
{"id":"FORMAT-065","claim":"On an M4 running macOS 27 with coremltools 9.0, a probe of 168 MIL operations built 130 single-op models and found 100 of them ANE-supported, or 76.9 percent.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-001-ane-op-map/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["operations","coverage","measurement"],"entities":["M4","ane-probe","MLComputePlan"],"evidence":"python -m ane_probe scan on 2026-09-20; 38 ops skipped because the probe could not build them, which is a probe limitation and not evidence about the ANE","caveat":"MLComputePlan is static compiler analysis and does not prove runtime placement","contested":false,"split":"holdout"}
{"id":"FORMAT-066","claim":"Every dense-transformer operation probed on this M4 was ANE-capable: matmul, linear, conv, add, mul, sub, softmax, gelu, relu, layer_norm, gather, transpose, reshape, reduce_mean, exp, erf, rsqrt and pow.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-001-ane-op-map/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["operations","coverage","transformers"],"entities":["M4","MIL"],"evidence":"the scan's per-op supported column lists ANE for each of these ops","caveat":"eligibility from static analysis only; a full model can still be placed on GPU or CPU","contested":false}
{"id":"FORMAT-067","claim":"The ops not ANE-supported in our M4 scan are the transcendentals (acos, asin, atanh, cosh, sinh, tan), index and control-flow ops (argsort, non_zero, one_hot, shape, cumsum, reduce_argmax, reduce_argmin, reduce_prod), the scatter family, the RNN family (gru, lstm, rnn), and misc ops including random_*, non_maximum_suppression, band_part, reverse_sequence, sliding_windows and mod.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-001-ane-op-map/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["operations","coverage","gaps"],"entities":["M4","MIL"],"evidence":"the 30 non-supported rows of ane_support_results.csv","caveat":"measured on M4/macOS 27.0/coremltools 9.0 only; op support is family- and OS-dependent","contested":false}
{"id":"FORMAT-068","claim":"In the ane-probe output the 'preferred' column reads CPU on essentially every row and is meaningless, because single-op models pay ANE transfer overhead so the compiler prefers CPU.","kind":"gotcha","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-001-ane-op-map/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["operations","measurement","gotcha"],"entities":["ane-probe","MLComputePlan"],"evidence":"preferred counts over our 168-row scan: CPU 128, ANE 1, unknown 1, blank 38","caveat":"only the supported column is informative for eligibility","contested":false}
{"id":"FORMAT-069","claim":"Three-dimensional convolution is advertised by an ANE hardware capability byte and recognized by the compiler frontend, yet fails backend lowering on every device mask.","kind":"gotcha","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["operations","capability","gotcha"],"entities":["3D convolution","ane compiler"],"evidence":"Chapter 4.4 'Attested is not reachable'; the frontend recognizes it and lowering fails with a not-implemented rejection","caveat":"decompile-derived plus on-device sweep in the paper","contested":false}
{"id":"FORMAT-070","claim":"A hardware capability bit, a frontend acceptance, or a validator pass is only a claim about one layer of the ANE stack; only a compile-and-run on the target confirms an operation at the layer that executes it.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["operations","method","capability"],"entities":["ANE","capability byte"],"evidence":"Chapter 4.4 and 4.6; on M1 the top-k, sort and dynamic-slice validators are callable but code generation rejects all three","caveat":"the paper reports a reachable rather than an advertised surface","contested":false}
{"id":"FORMAT-071","claim":"The same ANE operation can be available on one compile route and rejected on the other: whole-tensor argument-maximum is gated to A15 on the intermediate-language route yet runs on M1 through the bridge route because its hardware feature byte is set on A13.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["operations","compile-routes","capability"],"entities":["argmax","A13","bridge route"],"evidence":"Chapter 4.5 and table 4.2 (feature byte 0x4f2 set from A13/M1 onward)","caveat":"decompile-derived; the two routes have different capability gates on the same chip","contested":false}
{"id":"FORMAT-072","claim":"Native sin and cos arrive only with the A15 generation; M1 and A14 reject them and decompose on the host.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["operations","trig","gating"],"entities":["sin","cos","A15"],"evidence":"Chapter 4.2 table 4.1 and Appendix A.13","caveat":"family-gated, so a compile against an earlier target rejects them","contested":false}
{"id":"FORMAT-073","claim":"The ANE texture-engine operations (hardware resize/sampler, crop-resize, resample, affine) are absent on the M1 and arrive with the A14 generation.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["operations","texture-engine","gating"],"entities":["M1","A14","texture engine"],"evidence":"Chapter 4.2 table 4.1; feature byte 0x81d","caveat":"community docs list upsampling as working on the ANE in some models, which is not the same as the hardware sampler path","contested":false}
{"id":"FORMAT-074","claim":"The ANE has no hardware path on any family from M1 to M5 for reduce_prod, the scatter family, mod, one_hot, non_zero, band_part, reverse_sequence, shape, sliding_windows, logical and/or/xor, the gru/lstm/rnn cells, inverse and hyperbolic trig, and the non-uniform random-sampling ops.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["operations","no-path"],"entities":["ANE","MIL"],"evidence":"Chapter 4.2; these must be computed off-engine or reformulated (product reduction via log-sum-exp, logical-and via minimum, recurrent cells via unrolled fixed-trip-count graphs)","caveat":"decompile-derived plus measurement on M1/M2/M5","contested":false,"split":"holdout"}
{"id":"FORMAT-075","claim":"The ANE's gather path on M1 is a software path valid only when the data batch and depth are 1, the index channel is 3, and the index width and depth are 1; outside that envelope the compiler aborts rather than falling back.","kind":"gotcha","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["operations","gather","gotcha"],"entities":["gather","M1"],"evidence":"Chapter 4.7","caveat":"M1-specific envelope","contested":false}
{"id":"FORMAT-076","claim":"The community layer-level list of ANE-unsupported layers names custom layers, RNN layers such as LSTM and GRU, gather, dilated convolutions, broadcastable and ND layer types, certain broadcasting operations, pooling with kernel size above 13 or stride above 2, and upsampling with scaling factor above 2.","kind":"fact","confidence":"claimed","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/unsupported-layers.md","source_type":"secondary","retrieved":"2026-09-23","topic":["operations","layers","community"],"entities":["Core ML","LSTM","upsampling"],"evidence":"the document's own warning states the information is incomplete and possibly wrong, and that some entries are guesses","caveat":"layer-level and version-dependent; the page is explicitly a starting point rather than authoritative","contested":false}
{"id":"FORMAT-077","claim":"Core ML broadcastable and ND layers can often be replaced by older layer types that do lower to the ANE, for example AddBroadcastableLayer to AddLayer, MultiplyBroadcastableLayer to MultiplyLayer/ScaleLayer, ConcatND to Concat, and LoadConstantND to LoadConstant.","kind":"procedure","confidence":"claimed","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/unsupported-layers.md","source_type":"secondary","retrieved":"2026-09-23","topic":["operations","model-surgery","procedure"],"entities":["coremltools","AddBroadcastableLayer"],"evidence":"the document lists each substitution, and model-surgery.md gives a coremltools snippet that rewrites addBroadcastable layers into add","caveat":"community guidance with an explicit accuracy warning; no benchmark attached","contested":false}
{"id":"FORMAT-078","claim":"Placement of a computation on the ANE is a property of how the computation is expressed, not of what it computes: a fused RMSNorm is fully ANE-eligible while its arithmetically identical decomposition is CPU-only.","kind":"fact","confidence":"documented","source":"https://arxiv.org/abs/2608.22110","source_type":"primary","retrieved":"2026-09-23","topic":["placement","operation-expression","compile"],"entities":["RMSNorm","ANE","Core ML"],"evidence":"abstract of arXiv:2608.22110, supported in that work by a 64-shape sweep of LLM primitives recording per-operation device support","caveat":"only the abstract was reachable; the full-text HTML URL returned a stub, so the surrounding detail could not be read","contested":false}
{"id":"FORMAT-079","claim":"A 25.85M-parameter conv-heavy fp16 model was assigned entirely to the CPU by CoreML while the same graph in int8 or 2-bit returned to about 83 percent ANE residency and ran 1.8 to 2.2 times faster.","kind":"measurement","confidence":"documented","source":"https://arxiv.org/abs/2608.22110","source_type":"primary","retrieved":"2026-09-23","topic":["placement","quantization","residency"],"entities":["ANE","Core ML","int8"],"evidence":"abstract: ANE memory-controller byte counters confirmed zero bytes through the engine for the fp16 graph","caveat":"abstract-level claim; the counters are that paper's own measurements","contested":false}
{"id":"FORMAT-080","claim":"Core ML's computeUnits setting is a placement hint rather than a guarantee, and the caller is not told which device ran each segment of a model.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["placement","coreml","gotcha"],"entities":["MLModelConfiguration","computeUnits"],"evidence":"Chapter 1.1 listing 1 with the comment 'a hint, not a guarantee' and 'The caller is not told which device ran each segment'","caveat":"Apple's own documentation says the same in softer terms","contested":false}
{"id":"FORMAT-081","claim":"A Core AI graph can compile but still run on the CPU, and the documented fix is an explicit --preferred-compute neural-engine flag.","kind":"gotcha","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/compute-units-and-authoring.md","source_type":"secondary","retrieved":"2026-09-23","topic":["placement","coreai","gotcha"],"entities":["coreai-build","neural-engine"],"evidence":"the note cites Apple's own skills/.../common_issues.md lines 109-112 for the fix and states 'iOS implies ANE is the default tendency, not a guarantee'","caveat":"distilled by our project from Apple skill files and WWDC transcripts","contested":false}
{"id":"FORMAT-082","claim":"The ANE is a native fp16 engine: the frontend accepts fp32, int32 and bf16 type annotations but the backend does not implement them, so those annotations do not reach the silicon as wider arithmetic.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["numerics","dtypes","precision"],"entities":["fp16","bf16","ANE"],"evidence":"Chapter 4.3: the compiler rejects a cast to int32 on the M1 and bf16 is not usable as a program input or output dtype; bf16 is not among the eleven program-I/O dtype codes","caveat":"the running accumulator is wide (fp32 class) even though the datapath is fp16","contested":false}
{"id":"FORMAT-083","claim":"The community reference states the ANE appears to use float16 for everything and that there is no evidence the ANE performs convolution directly with quantized weights, with 8-bit support in Core ML limited to matrix multiplication and it being unknown whether that runs on the ANE at all.","kind":"open-question","confidence":"claimed","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/16-bit.md","source_type":"secondary","retrieved":"2026-09-23","topic":["numerics","quantization","contested"],"entities":["ANE","int8"],"evidence":"the document states 'there is no evidence to suggest the ANE currently does this' and 'It's unknown whether such 8-bit operations are actually performed on the ANE'","caveat":"undated community page; it conflicts with the reverse-engineered account that the array has a double-int8 compute mode running about 1.4-2x the fp16 rate","contested":true}
{"id":"FORMAT-084","claim":"The ANE array has a double-int8 compute mode that runs roughly 1.4 to 2 times the fp16 rate, and int8 weights therefore act as a compute lever as well as a bandwidth one.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["numerics","int8","compute"],"entities":["ANE","int8"],"evidence":"Chapters 9 and 20; the lane width is 4 output channels per cycle in the default fp16 path and 8 in the int8 fast path","caveat":"decompile-derived plus measurement; this conflicts with the older community claim that there is no evidence of quantized convolution on the ANE","contested":true,"split":"holdout"}
{"id":"FORMAT-085","claim":"The int8 compile flag on the ANE frontend quantizes weights and halves the streamed weight bytes but does not emit the eight-channel int8 compute path, so it changes bandwidth rather than compute rate.","kind":"gotcha","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["numerics","int8","gotcha"],"entities":["ANE","int8"],"evidence":"Chapter 20.7: the flag leaves the multiply-accumulate in fp16; int8 reaches about 1.5x only where the weight is large enough to stream from main memory","caveat":"decompile-derived from the M1 frontend path","contested":false}
{"id":"FORMAT-086","claim":"A fused ANE convolution's activation is implemented as a 33-segment programmable piecewise-linear lookup table rather than as arithmetic.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["operations","activation","lut"],"entities":["activation lookup","ANE"],"evidence":"Chapter 22.2: a padded, biased, activated convolution emits as one backend operation with the activation as a 33-segment piecewise-linear table, and Chapter 4.1 says chap. 26 covers reaching an arbitrary pointwise function through it","caveat":"decompile-derived","contested":false}
{"id":"FORMAT-087","claim":"The ANE compiler emits a per-layer fixed overhead of 44 cycles that is added to every layer's execute cycles, and a live M1 compile costs against 8 active engines on 1 cluster.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","cost-model","cycles"],"entities":["ANECompiler","GetTotalNumberOfActiveNEs"],"evidence":"Chapter 20.6 table 20.6, captured live during an M1 compile, also listing candidate split geometries of 1, 4 and 16 engines","caveat":"decompile-derived from one live M1 compile; the 8 active engines is a model-internal figure, not the registry core count","contested":false}
{"id":"FORMAT-088","claim":"The compiler accepts a matrix multiply only when the depth axis is 1 on both operands, rejecting with the message 'depth > 1 is not supported for MatMult'.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["operations","matmul","constraints"],"entities":["anec.matmul","ANE"],"evidence":"Chapters 4.7 and 22.4; the matmul validator also requires two inputs, Cout of the output equal to the first input's channel count, and the first input's output-channel bytes to fit kernel memory ('can not fit the Kmem')","caveat":"decompile-derived validator behaviour","contested":false}
{"id":"FORMAT-089","claim":"Tensor rank is capped at five on the ANE, the frontend rejects a rank-6 tensor with the message 'tensor rank 6 exceeds the ANE maximum of 5', and a rank-5 batched matrix multiply builds but is rejected by the on-device backend.","kind":"gotcha","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","limits","rank"],"entities":["MIL","ANE"],"evidence":"Chapter 4.8 table 4.4, compile-only probes on the M1 separating frontend rejects from on-device compiler rejects","caveat":"measured compile-only on M1; a zero-size dimension is the one degenerate shape the on-device validator rejects as a type mismatch","contested":false}
{"id":"FORMAT-090","claim":"Program inputs to the ANE compiler are fp16 or uint8 only, where uint8 supplies only the in-graph dequantization path for an integer image input.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","input","dtypes"],"entities":["ANE","fp16","uint8"],"evidence":"Chapter 4.8 table 4.4: fp16 accepted, uint8 into arithmetic rejected on-device, fp32/int32/bf16/int8 rejected by the frontend with 'dtype must be fp16 or uint8'","caveat":"M1 probe; the entitled framework route supplies an image-input descriptor the direct route lacks","contested":false}
{"id":"FORMAT-091","claim":"A tensor axis is capped at 16384 on M1 through A15 and 65536 on A16 and later, applied per axis rather than to the last axis alone.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["limits","shape","cross-silicon"],"entities":["M1","A16","M5"],"evidence":"Chapter 4.8 ('any axis = 16385' rejected with 'exceeds ANE family 2's max dimension 16384') and Appendix A.1; convolution Cin and Cout escape the cap (16385 compiles)","caveat":"M1 measured, A16 and later from the per-chip tables","contested":false}
{"id":"FORMAT-092","claim":"The ANE frontend bounds convolution kernel width at 15 while the fp16 datapath caps it lower at 13, so an fp16 kernel of width 14 or 15 still rejects at lowering.","kind":"gotcha","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["limits","convolution","gotcha"],"entities":["conv","M1"],"evidence":"Chapter 4.8: frontend rejects kW=16 with 'kW must be <=15'; the per-chip limit table gives max kernel width fp16 = 13 on M1 and 16 on A14 and later","caveat":"M1 measured; the kernel height is unconstrained, so a 16x3 kernel compiles and a 3x16 kernel does not","contested":false}
{"id":"FORMAT-093","claim":"The ANE compiles Winograd F(2x2,3x3) and F(4x4,3x3) transforms automatically for eligible dense 3x3 stride-1 convolutions, replacing 36 direct multiplies per 2x2 output tile with 16.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","winograd","convolution"],"entities":["Winograd","CanUseWinogradMode"],"evidence":"Chapters 13 and 20.5; eligibility requires the per-chip Winograd-enable bit, kernel format eligibility, one axis equal to 3, unit stride, and enough work to amortize the transform","caveat":"decompile-derived; eligibility is not selection, since the compiler also cost-compares against direct convolution and accumulator double-buffering","contested":false,"split":"holdout"}
{"id":"FORMAT-094","claim":"The ANE output-channel-group size is computed as min(floor_pow2(8 / (kW*kH*kD)), byte_cap) from an accumulator budget of 8 work units, and the pass count is ceil(Cout / OCG).","kind":"definition","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["execution-model","tiling","ocg"],"entities":["ComputeMaxOcgSize","OCG"],"evidence":"Chapter 20.4 with listing 32; byte cap 32/16/8 bytes per kernel element by weight format at HAL 0x388/0x390/0x398","caveat":"the accumulator budget of 8 is uniform across all chips in the decoded set","contested":false}
{"id":"FORMAT-095","claim":"A 1x1 convolution on the ANE has a kernel-element count of 1 and therefore admits a much larger output-channel group than a 3x3 convolution, which is the compiler-side reason a linear layer becomes a 1x1 conv.","kind":"fact","confidence":"inferred","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["execution-model","conv1x1","tiling"],"entities":["OCG","conv1x1"],"evidence":"Chapter 20.4 states the 1x1 admits a large group and the 3x3 roughly nine times smaller, needing more input passes; Chapter 17 and the ReplaceMatmulWithConv pass independently say a linear layer is rewritten as a 1x1 conv","caveat":"the causal link between group size and the linear-to-conv rewrite is our inference; both facts are documented separately","contested":false}
{"id":"FORMAT-096","claim":"Every ANE task descriptor is versioned per silicon generation and born with one of 14 versioned descriptor structs, so any tool reading task-descriptor bytes must dispatch on the version number rather than assume a fixed layout.","kind":"gotcha","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["task-descriptor","versioning","gotcha"],"entities":["ZinAneTdHw_v10"],"evidence":"Chapter 23.3: 'The descriptor layout is versioned per silicon generation... byte offsets, register addresses, and field widths move between versions'","caveat":"decompile-derived","contested":false}
{"id":"FORMAT-097","claim":"Task-descriptor register offsets reported for an M3 (TD+0x004, TD+0x078 core bases, TD+0x1f0 L2 stride, TD+0x214 L2 result base) are a different address space from the M1 v10 struct-base offsets decoded in arXiv:2606.22283 (kernel-and-common +0x2c, tile DMA +0x150, L2 result +0x360).","kind":"gotcha","confidence":"inferred","source":"https://eiln.github.io/posts/ane-dma.html","source_type":"primary","retrieved":"2026-09-23","topic":["task-descriptor","registers","contested"],"entities":["M3","M1","ZinAneTdHw_v10"],"evidence":"the two sources give incompatible offsets for differently-named fields on different generations (M3 register image vs M1 v10 struct base), and the paper states the M1 switch for 0x1f0 semantics describes a HAL table field rather than a descriptor field","caveat":"neither source decodes the other's generation; do not conflate the two offset spaces","contested":true}
{"id":"FORMAT-098","claim":"After a failed ANE compile you should wait about 15 seconds before the next one, because a failure restarts the shared compiler service and a burst of failures faster than the restart interval stalls unrelated compiles.","kind":"gotcha","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","gotcha","service"],"entities":["ANECompilerService"],"evidence":"Chapter 19, 'detecting a failed compile, wait at least one restart interval, roughly 15 seconds, before the next compile'","caveat":"M1 measurement in the paper; the compile service is shared across processes","contested":false}
{"id":"FORMAT-099","claim":"A combinatorial subgraph search in the ANE compiler is exponential in the width of parallel branches reconverging into one consumer, and a single cluster with roughly twelve or more such branches is worth flagging at build time.","kind":"gotcha","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","gotcha","scheduling"],"entities":["ANECompiler","subgraph search"],"evidence":"Chapter 19.5: the search has no iteration cap but an internal time budget abandons it and falls back to a cheaper partition, plateauing the worst measured fan-in at about 9.2 seconds on M1","caveat":"M1 measurement; the budget bail is not guaranteed across compiler versions","contested":false}
{"id":"FORMAT-100","claim":"The ANE compiler targets per-family code generation with a Family enum of A11Legacy 0, A12 1, A13 2, A14 3, A15 4, A16 5, A17 6, A18 7, and the M1 compiles as A13 while the M5 compiles as A17.","kind":"fact","confidence":"documented","source":"https://arxiv.org/html/2606.22283v1","source_type":"primary","retrieved":"2026-09-23","topic":["compile","family","targets"],"entities":["aFam","M1","M5"],"evidence":"Chapter 35 mlir::anec::Family enum and the family floor checks, plus the M(n)=H(n+12) relation","caveat":"decompile-derived","contested":false}
{"id":"FORMAT-101","claim":"A single shipping Apple vision filter carries exactly five engine tables, H13 through H17, one per Mac engine generation, which makes per-generation programs an on-disk property of the OS rather than a theoretical one.","kind":"measurement","confidence":"measured","source":"/System/Library/PrivateFrameworks/VideoProcessing.framework/Versions/A/Resources/cnn_frame_enhancer_96p.H17.espresso.hwx","source_type":"our-own","retrieved":"2026-09-23","topic":["artifact","hwx","cross-silicon"],"entities":["VideoProcessing.framework","H13","H17"],"evidence":"the directory contains cnn_frame_enhancer_{96p,192p,320p,720p}.H13/.H14/.H15/.H16/.H17.espresso.hwx, and there are 65 *.hwx files under /System/Library on this machine","caveat":"counts obtained on this macOS 27 install","contested":false}
{"id":"FORMAT-102","claim":"A Core AI compile with neural-engine preferred records the flags useANELLIR true, enableANECValidationWorkflow true and optimizationLevel 1 in the package manifest's compilation descriptor.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/work/exports/von-retest/aot/von-1.0_v1_float16_s256_ane.h16g.aimodelc/main-h16g-delegates/MPSGraph/mpsExecutable.mpsgraphpackage/manifest.plist","source_type":"our-own","retrieved":"2026-09-23","topic":["artifact","aimodelc","compile"],"entities":["Core AI","MPSGraph","ANELLIR"],"evidence":"manifest.plist Package Version 7.0.63 records an ANERegionsHash keyed by h16g and the compilation descriptor quoted above","caveat":"one model, one toolchain build; the manifest schema is not documented by Apple","contested":false}
{"id":"FORMAT-103","claim":"The stats.json emitted next to an AOT-compiled ANE bundle reports the storage and compute type census and an operationDistribution for the graph, which for our Von-1.0 ANE export was dominated by constant (1624), reshape (297), slice (253), broadcast_in_dims (235), mul (235) and broadcasting_mul (231) around 170 batch_matmul and 170 broadcasting_batch_matmul operations.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/work/exports/von-retest/aot/von-1.0_v1_float16_s256_ane.h16g.aimodelc/stats.json","source_type":"our-own","retrieved":"2026-09-23","topic":["artifact","stats","operations"],"entities":["Von-1.0","Core AI"],"evidence":"read the full 1470-byte file; storageTypes are Float16 395899912, Bool 65536, UInt32 75, Int32 36, Float32 2, UInt64 1","caveat":"this census is of the graph as handed to the compiler, not of the lowered engine program","contested":false}
{"id":"FORMAT-104","claim":"Apple's stated ANE history is 0.6 TFLOP/s fp16 in the A11 (2017) and 15.8 TFLOP/s for the fifth-generation 16-core ANE in 2021, a 26-fold increase.","kind":"fact","confidence":"documented","source":"https://machinelearning.apple.com/research/apple-neural-engine","source_type":"primary","retrieved":"2026-09-23","topic":["hardware","history","throughput"],"entities":["A11","A15","ANE"],"evidence":"the article's 'The Apple Neural Engine' section and Figure 1","caveat":"vendor peak figures; the reverse-engineered account measures lower sustained rates and a different core count","contested":false}
{"id":"FORMAT-105","claim":"Apple's official guidance for ANE models is to chunk large attention tensors into explicit single-head functions and to avoid reshape and transpose operations, which are likely to trigger memory copies because at least one axis of an ANE buffer is not packed.","kind":"procedure","confidence":"documented","source":"https://machinelearning.apple.com/research/apple-neural-engine","source_type":"primary","retrieved":"2026-09-23","topic":["authoring","attention","layout"],"entities":["multihead attention","ANE"],"evidence":"Principles 2 and 3 of the article, with the einsum bchq,bkhc->bkhq form used to avoid intermediate transpose and reshape","caveat":"Apple's guidance for its own reference implementation; the memory-copy cost is stated rather than measured there","contested":false}
{"id": "FORMAT-106", "claim": "The Core AI specialization cache persists under ~/Library/Caches/coreai-cache/<key>/ in two layouts — osbuild (<OSBUILD>/<process>/<modelHash64 lower>/<optsHash64 upper>/{model.aimodelx|X.aimodel}/…) and pyver (<python-version>/<modelHash64>/<X>.aimodel>/…) — each plan being a *.mpsgraphpackage holding manifest.plist, original_model_N.mpsgraph (mps-dialect MLIR bytecode; magic 4d4cef52, producer MLIR22.0.0git, bytecode v6), specialized_model_N.mpsgraph (adds the placement dialect: main_*_ANE_region_N_0 and main_*_GPU_region_N symbols), binary_0.llir.bundle (per-ANE-region LLIR), optional binary_0.hwx, and resources.bin.", "kind": "fact", "confidence": "measured", "source": "results/EXP-026-ane-kitchen/results/coreai_cache_format.md", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["coreai", "cache", "format", "placement"], "entities": ["coreai-cache", "mpsExecutable.mpsgraphpackage", "original_model_0.mpsgraph", "specialized_model_1.mpsgraph", "MLIR22.0.0git", "placement"], "evidence": "bench/coreai_cache.py census over 198 plans (coreai_cache_census.json); string-dictionary decode of original vs specialized", "caveat": "the OS-build vs python-version key is the only observed split; a *.delegates/BNNS dir holds a different (bnns.ir) container with no MLIR string dictionary", "contested": false}
{"id": "FORMAT-107", "claim": "Core AI's cached manifest.plist is a versioned dict (Package Version → 7.0.63) whose 'Optimized Modules' list carries the compiler descriptor JSON at index 0 (entryFunctionName, deviceDescriptor [0,40,\"h17c\"], inputShapes, and ~30 compilationDescriptor flags including useANELLIR, allowedComputeDevices and preferredDevice), alongside Original (the source filename), ANERegionsHash (arch-keyed plan hashes) and 'GPU adapter present' — which is \"NO\" on this route, meaning no GPU-fallback compiler was packaged, NOT that the plan is ANE-only: the ANE-routed granite plan measures 13 ANE + 14 GPU regions.", "kind": "fact", "confidence": "measured", "source": "results/EXP-026-ane-kitchen/results/coreai_cache_format.md", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["coreai", "cache", "format", "compilation"], "entities": ["manifest.plist", "Optimized Modules", "deviceDescriptor", "ANERegionsHash", "useANELLIR", "GPU adapter present"], "evidence": "plistlib decode of the granite h17c plan; descriptor JSON found at Package Version/7.0.63/Optimized Modules[0] and repeated under Used In Cache[0]", "caveat": "package version observed 7.0.63 on 26A434 only; descriptor key meanings (inputShapes packed ints) decoded structurally but not fully interpreted", "contested": false}
{"id": "FORMAT-108", "claim": "The cached Core AI mpsgraph bytecode can be printed as readable MLIR: a stub dialect plugin clears the private dialects' bytecode-version and resource interfaces, and a bytecode rewrite (bench/mlir_bytecode.py rewrite, --pad-attrs for plans whose unknown-op 'properties' bytes look like an out-of-range attribute index) converts the private dialects' custom-encoded attribute/type entries to textual placeholders (loc(unknown)/i64), after which mlir-opt --load-dialect-plugin --allow-unregistered-dialect prints the IR — both cached plans now recover: the original shows the model source (mps.module/mps.func/mps.constant with real dense<> constants, tensor shapes and SSA values) and the specialized shows the placement (module mps.aneArch \"h17c\", mps.aneRegionsSHA, mps.deviceGPUCoreCount 40, every ANE/GPU region function with its memref/tensor signature), while private attribute VALUES that use the custom encoding are stubbed.", "kind": "procedure", "confidence": "measured", "source": "results/EXP-026-ane-kitchen/results/p2b_model_src_ir.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["format", "tooling", "mlir", "placement"], "entities": ["mlir-opt", "mlir_bytecode.py", "DialectPlugin", "specialized_model_1.mpsgraph", "original_model_0.mpsgraph", "mps.aneArch", "mps.constant", "mpsx.ane"], "evidence": "harness/p2b_mps_dialect_plugin.cpp + bench/mlir_bytecode.py against the cached granite h17c plan: 934 lines of IR, 0 errors; all 26 ANE/GPU region functions and the full model-source op graph recovered; wall path recorded in p2b_mps_dialect_wall.txt", "caveat": "the original plan needs --pad-attrs (unknown ops read 'properties' as an attribute index; padding absorbs the non-index bytes); MLIR/LLVM-version-specific (Homebrew llvm@22); that the container is MLIR bytecode is already public (LLVM MPS-dialect RFC + mpsgraphtool, LANDSCAPE-077) — the novelty is the private aicode/placement dialects and the printing technique", "contested": false}
```