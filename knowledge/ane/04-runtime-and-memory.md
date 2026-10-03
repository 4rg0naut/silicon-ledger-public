# Runtime and memory: how data actually gets in and out of the ANE

This file is about the data path, not the API surface. It covers the IOSurface buffer model the
ANE requires, the exact compile/bind/evaluate sequence the direct-access projects actually run,
the single-input constraint and how projects work around it, the dtype and layout rules at the
boundary, the request lifecycle including the per-process compile limit, and a minimal recipe
from "compiled program" to "numbers came out".

Everything below is drawn from code or documentation that exists today; every code block names
its source project. Nothing here was executed. Where projects disagree, both positions are
recorded.

---

## 1. IOSurface — the buffer the ANE will accept

**What it is.** IOSurface is a *public* Apple framework (`/System/Library/Frameworks/IOSurface.framework`),
not a private API. It is a reference-counted, page-aligned, kernel-tracked buffer that can be
mapped into more than one client at once — CPU, GPU, and the ANE. That is exactly the property
the ANE needs: the NPU cannot be handed an arbitrary `malloc`'d pointer, so every direct-ANE
project allocates its tensors as IOSurfaces and lets the private framework wrap them.

**Why the wrapper classes are private.** The IOSurface itself is Apple-documented. What is not
documented is the ANE-side binding: `_ANEIOSurfaceObject`, `_ANERequest`, and (for program
chaining) `_ANEIOSurfaceOutputSets`. Those are resolved at runtime by name from
`AppleNeuralEngine.framework`:

```objc
// Source: thebasedcapital/ane-infer, crates/ane-bridge/objc/ane_runtime.m
static Class g_ANEDesc   = nil;  // _ANEInMemoryModelDescriptor
static Class g_ANEInMem  = nil;  // _ANEInMemoryModel
static Class g_ANEReq    = nil;  // _ANERequest
static Class g_ANEIO     = nil;  // _ANEIOSurfaceObject
static Class g_ANEClient = nil;  // _ANEClient (for direct eval bypass)
```

and the same four classes appear, identically, in maderix/ANE (`inmem_basic.m`, `bridge/ane_bridge.m`,
`training/training_dynamic/config.h`) and in johnmai-dev/ANE-LM (`core/ane_runtime.cpp`). This is
the convergent shape of the community's understanding: descriptor → in-memory model → request →
IOSurface-wrapped buffers.

**How the surface is actually allocated.** Every project uses the same dictionary, with the width
field abused as a plain byte count and `height = 1`. There is no pixel semantics here:

```objc
// Source: maderix/ANE, inmem_basic.m (identical helper in ane-infer and ANE-LM)
IOSurfaceRef create_surface(size_t bytes) {
    return IOSurfaceCreate((__bridge CFDictionaryRef)@{
        (id)kIOSurfaceWidth:           @(bytes),
        (id)kIOSurfaceHeight:          @1,
        (id)kIOSurfaceBytesPerElement: @1,
        (id)kIOSurfaceBytesPerRow:     @(bytes),
        (id)kIOSurfaceAllocSize:       @(bytes),
        (id)kIOSurfacePixelFormat:     @0
    });
}
```

`kIOSurfacePixelFormat: 0` means "no pixel format"; the buffer is treated as bytes. maderix's
`inmem_basic.m` allocates `ch * sp * 4` bytes, i.e. fp32-sized surfaces, while the training
code stores `_Float16` on the surface (`channels * sp * sizeof(_Float16)`) — both are accepted.
The maderix README states fp16 direct I/O is ~37% faster than fp32, a project claim rather than
a published benchmark.

**How CPU, GPU and ANE share it without copying.** The host writes by locking the surface and
memcpy'ing into its base address:

```objc
// Source: thebasedcapital/ane-infer, ane_runtime.m
void ane_write_input(ANEKernel *k, int idx, const void *data, size_t bytes) {
    IOSurfaceLock(k->ioInputs[idx], 0, NULL);
    memcpy(IOSurfaceGetBaseAddress(k->ioInputs[idx]), data, bytes);
    IOSurfaceUnlock(k->ioInputs[idx], 0, NULL);
}
```

The request that is handed to `evaluateWithQoS:` refers to those *same* surfaces, not to a copy.
So "zero-copy" here means: the host fills the buffer, the ANE reads it in place, and the host
reads the output surface in place afterwards. maderix's `gpu_ane_share.m` and
`gpu_prefill_ane_decode.m` extend the same trick across accelerators — "GPU↔ANE zero-copy
pipeline via shared IOSurface (GPU prefill → ANE decode)". An independent measurement of what
that handoff costs is quoted in the coreai-model-zoo knowledge base at roughly **2.3 ms per
IOSurface round trip**, cited there to arXiv 2603.06728.

**The handoff classes, specifically.**

| Class | Role | Selector used |
| --- | --- | --- |
| `_ANEIOSurfaceObject` | wraps one `IOSurfaceRef` as a request buffer | `+objectWithIOSurface:` |
| `_ANERequest` | binds input/output buffer arrays, indices, optional weights buffer, procedure index | `+requestWithInputs:inputIndices:outputs:outputIndices:weightsBuffer:perfStats:procedureIndex:` |
| `_ANEIOSurfaceOutputSets` | output-buffer sets used by the chaining path | `+objectWithstatsSurRef:outputBuffer:` |

The last row is the interesting one, because it is a *correction*. ane-infer reports that
`ANEProgramChainingPrepare()` failing with **error 15** was not a firmware limit but the wrong
factory method:

```
Before: outputSetsWithBuffers:@[buf_out]                 → error 15
After:  objectWithstatsSurRef:ioStats outputBuffer:@[buf_out]  → SUCCESS
```

Both `prepareChainingWithModel:` and the direct `doPrepareChainingWithModel:` then succeed;
`buffersReady` "remains blocked — the next frontier". That is a single project's result, stated
as such.

Finally, the request object is built once and reused for every evaluation, which matters for
latency: the comment in ane-infer's kernel struct is literally `// _ANERequest (reused across
evals)`, and ANE-LM does the same.

---

## 2. The allocation and binding flow, step by step

This is the sequence that maderix/ANE, ANE-LM, ane-infer and libane all implement. Step 6 (the
temp directory) is the one that surprises people.

1. **Load the framework by handle.** `dlopen("/System/Library/PrivateFrameworks/AppleNeuralEngine.framework/AppleNeuralEngine", RTLD_NOW)`, then resolve the private classes with `NSClassFromString`.
2. **Get MIL text.** Either from a Core ML-compiled model's `model.mil`, or generated at runtime. maderix's PoC compiles an `.mlpackage` first and reads the MIL out of it; ANE-LM builds MIL strings in C++ (`mil_gen_matmul`, `mil_gen_fused_ffn`).
3. **Build the weight dictionary.** Keys are the *virtual* paths referenced inside the MIL, values are `{offset, data}`:
   ```objc
   // Source: maderix/ANE, inmem_basic.m
   NSDictionary *wdict = @{
       @"@model_path/weights/weight.bin": @{@"offset": @64, @"data": weightBlob}
   };
   ```
4. **Create the descriptor and the model.**
   ```objc
   // Source: maderix/ANE, inmem_basic.m
   Class Desc = NSClassFromString(@"_ANEInMemoryModelDescriptor");
   Class IMM  = NSClassFromString(@"_ANEInMemoryModel");
   id desc  = ((id(*)(Class,SEL,id,id,id))objc_msgSend)(
       Desc, @selector(modelWithMILText:weights:optionsPlist:), milData, wdict, nil);
   id model = ((id(*)(Class,SEL,id))objc_msgSend)(IMM, @selector(inMemoryModelWithDescriptor:), desc);
   ```
5. **Ask the model for its cache key.** `hexStringIdentifier` returns the identifier the compiler also uses to name a scratch directory.
6. **Materialise the program on disk.** The compiler needs the MIL and the weights as real files under `$TMPDIR/<hexStringIdentifier>/`:
   ```objc
   // Source: maderix/ANE, inmem_basic.m
   id hexId = ((id(*)(id,SEL))objc_msgSend)(model, @selector(hexStringIdentifier));
   NSString *tmpDir = [NSTemporaryDirectory() stringByAppendingPathComponent:hexId];
   [fm createDirectoryAtPath:[tmpDir stringByAppendingPathComponent:@"weights"]
       withIntermediateDirectories:YES attributes:nil error:nil];
   [milData writeToFile:[tmpDir stringByAppendingPathComponent:@"model.mil"] atomically:YES];
   [weightBlob writeToFile:[tmpDir stringByAppendingPathComponent:@"weights/weight.bin"] atomically:YES];
   ```
   ANE-LM uses `getenv("TMPDIR")` explicitly rather than `NSTemporaryDirectory()` but does the identical thing, walking the whole weight dictionary and stripping the `@model_path/` prefix to compute on-disk relative paths.
7. **Compile and load.**
   ```objc
   // Source: maderix/ANE, inmem_basic.m
   BOOL ok = ((BOOL(*)(id,SEL,unsigned int,id,NSError**))objc_msgSend)(
       model, @selector(compileWithQoS:options:error:), 21, @{}, &e);
   ok = ((BOOL(*)(id,SEL,unsigned int,id,NSError**))objc_msgSend)(
       model, @selector(loadWithQoS:options:error:), 21, @{}, &e);
   ```
   QoS 21 and an empty options dictionary are universal across projects. ane_bridge.m adds a retry: if `loadWithQoS:` fails it sleeps 100 ms and tries once more, commented "for ANE slot reclamation".
8. **Allocate the I/O surfaces and wrap them.**
   ```objc
   // Source: maderix/ANE, inmem_basic.m
   NSUInteger bytes = ch * sp * 4;
   IOSurfaceRef ioIn  = IOSurfaceCreate(...);   // see section 1
   IOSurfaceRef ioOut = IOSurfaceCreate(...);
   id wIn  = ((id(*)(Class,SEL,IOSurfaceRef))objc_msgSend)(AIO, @selector(objectWithIOSurface:), ioIn);
   id wOut = ((id(*)(Class,SEL,IOSurfaceRef))objc_msgSend)(AIO, @selector(objectWithIOSurface:), ioOut);
   ```
9. **Build the request.**
   ```objc
   // Source: maderix/ANE, inmem_basic.m
   id req = ((id(*)(Class,SEL,id,id,id,id,id,id,id))objc_msgSend)(AR,
       @selector(requestWithInputs:inputIndices:outputs:outputIndices:weightsBuffer:perfStats:procedureIndex:),
       @[wIn], @[@0], @[wOut], @[@0], nil, nil, @0);
   ```
10. **Fill the input surface, evaluate, read the output surface.**
11. **Tear down.** `unloadWithQoS:error:`, `CFRelease` on both surfaces, remove the temp directory. ANE-LM additionally deletes `$TMPDIR/<id>` unless its persistent compile cache is enabled.

**Weight blob format.** When weights travel as files rather than being generated inline, all
projects build the same 128-byte-prefixed blob. maderix's builder is the clearest:

```objc
// Source: maderix/ANE, training/training_dynamic/io.h
static NSData *build_blob_fp16(_Float16 *d, int cnt) {
    int ws=cnt*2, tot=128+ws;
    uint8_t *b=(uint8_t*)calloc(tot,1);
    b[0]=1;b[4]=2;b[64]=0xEF;b[65]=0xBE;b[66]=0xAD;b[67]=0xDE;b[68]=1;
    *(uint32_t*)(b+72)=ws;*(uint32_t*)(b+80)=128;
    memcpy(b+128,d,ws);
    return [NSData dataWithBytesNoCopy:b length:tot freeWhenDone:YES];
}
```

ANE-LM's `build_weight_blob` produces the same layout (magic `0xEF 0xBE 0xAD 0xDE` at +64, fp16
payload at +128) but converts from BF16 safetensors weights on the way in, via
`bf16_to_f16_vec`. The MIL then references the payload at `offset = 64`, which is why that
constant appears in every `BLOBFILE(...)` in ANE-LM's generated MIL.

**Persistent compile cache.** ANE-LM goes further than the others: after a successful
`compileWithQoS:` it writes a marker file under
`$HOME/Library/Caches/ane_lm/compiled_markers/<hexStringIdentifier>.ok`. On later runs it skips
compilation entirely and calls `loadWithQoS:` directly. `--no-ane-cache` turns the behaviour off;
maderix's bridge instead keeps a process-local `g_compile_count` counter.

**Multi-procedure programs.** One compiled program can carry several entry points, dispatched by
`procedureIndex`. ane-infer's bridge enumerates them via
`model → modelAttributes → "ANEFModelDescription" → "ANEFModelProcedures"` and pre-builds one
request per procedure. Its README claims this as a first-public success ("N functions in one
compiled program, dispatch by procedureIndex").

---

## 3. The single-input constraint, and what it forces

The strictest statement of the constraint comes from maderix's README limitations list:

> **Single-input constraint** — multi-input ANE requests cause 0x1d error; inputs packed into
> spatial dimension instead.

That is the position that shaped the async-weight training design. But it is *contested*, or at
least not universal: ane-infer's and ANE-LM's bridges both build request arrays sized `n_inputs`
and loop over them rather than hard-coding one, and libane's graph API accepts multiple tensors
(`libane_graph_add_input(s)`) that are lowered into a dispatch. Neither project documents a
working multi-input *dispatch* to the same compiled program, so the honest reading is: the
constraint is reported at the request level (`_ANERequest` with more than one input), while
multi-tensor graphs may be handled inside a single MIL program with one external input.

The workaround is the same everywhere and it is genuinely elegant: **concatenate everything along
the spatial (S) dimension**. maderix's dynamic-weight kernels take one input surface whose width is
activations *plus* weights, and slice them apart inside MIL. From `io.h`:

```c
// Source: maderix/ANE, training/training_dynamic/io.h
// sdpaFwd: [1, DIM, 1, SEQ + Q_DIM + KV_DIM + KV_DIM] fp16 — no Wo (separate kernel)
//   Wq: [DIM, Q_DIM], Wk: [DIM, KV_DIM], Wv: [DIM, KV_DIM]
#define SDPA_FWD_SP (SEQ + Q_DIM + KV_DIM + KV_DIM)
static void stage_sdpa_fwd_weights(IOSurfaceRef s, const float *Wq, const float *Wk, const float *Wv) {
    IOSurfaceLock(s, 0, NULL);
    _Float16 *buf = (_Float16*)IOSurfaceGetBaseAddress(s);
    for (int d = 0; d < DIM; d++) {
        cvt_f32_f16(buf + d*SDPA_FWD_SP + SEQ,                   Wq + d*Q_DIM, Q_DIM);
        cvt_f32_f16(buf + d*SDPA_FWD_SP + SEQ+Q_DIM,             Wk + d*KV_DIM, KV_DIM);
        cvt_f32_f16(buf + d*SDPA_FWD_SP + SEQ+Q_DIM+KV_DIM,     Wv + d*KV_DIM, KV_DIM);
    }
    IOSurfaceUnlock(s, 0, NULL);
}
```

The same pattern appears for the fused FFN, where the single input row per channel carries
`2*SEQ + 3*HIDDEN` elements: two activation segments and three weight matrices. The payoff is in
`train.m` — *the weights are arguments, not constants*, so the ten kernels are compiled once at
startup and re-staged by rewriting the surface. `compile_dynamic_kernels()` compiles
`sdpaFwd`, `woFwd`, `ffnFused`, `ffnBwdW2t`, `ffnBwdW13t`, `wotBwd`, `sdpaBwd1`, `sdpaBwd2`,
`qBwd`, `kvBwd` — once, for all layers. The README states the consequence plainly: "Weights change
without recompilation", one-time compile ~0.4 s.

ANE-LM reaches the same place from the other direction: its matmul kernel is genuinely
single-input, and every parameter is a compile-time weight blob, so it never needs more than one
input surface per program.

---

## 4. Precision and layout at the boundary

### Layout

The ANE wants **`[1, C, 1, S]`** — batch 1, height 1 — with the feature dimension in the channel
slot and the sequence/spatial dimension last. The community name for this is BC1S, and Apple's own
authoring rules in the coreai-model-zoo knowledge base state it as ANE-law: *"Layout: **BC1S**
`(B, C, 1, S)`"*, with projections expressed as **1×1 Conv2d** rather than `nn.Linear` — because
the conv engine on the ANE accumulates in fp32, which is the standard fix for fp16 matmul drift
over many layers.

libane's Graph IR states the same layout and its hard constraints precisely:

- `[1, C, 1, S]`; batch=1 and height=1 are non-negotiable in the graph API.
- **S must be a multiple of 16** (hardware alignment).
- **C must be ≤ 16384** for the graph API; larger channel counts (such as vocabulary projections)
  need raw MIL emission.
- Matmul `A[M,K]·B[K,N]` is expressed as A `[1,K,1,M]`, B `[1,N,1,K]` (weights), out `[1,N,1,M]`.

ANE-LM adds a minimum-spatial rule in code: `constexpr int ANE_SPATIAL = 32;` — "ANE minimum
spatial dimension required by hardware". Its `mil_gen_matmul` therefore declares
`tensor<fp16, [1, %d, 1, %d]>` with the second dimension fixed at 32, and `ane_matvec` writes
`in_base[idx]` at `idx = c * ANE_SPATIAL`, i.e. one live value per channel row, padded out to 32.

maderix's layout convention for a matmul is the transposed-weight form: weights live as a conv
weight tensor `[out_dim, in_dim, 1, 1]`, and the activation is `[1, in_dim, 1, S]`. The README
notes the CPU-side consequence: **channel-first CPU layout** — matching ANE's `[1,C,1,S]` — "eliminates all transpose overhead". Transposes are done once when weights are staged, not per step
(`transpose_weight` in `train.m`).

### Precision

- **libane graph API is fp16-only**: "Weights and activations are fp16 throughout. No quantization
  (int8, int4) support."
- **The ANE itself appears to be fp16 throughout.** hollance/neural-engine's `16-bit.md` states it
  as an observation ("The ANE appears to use float16 for everything"), with the practical
  consequence that activations above ~1e2 or below ~1e-4 lose precision, and that very small
  numbers may become 0. The same document contrasts this with the CPU, which uses fp32 (and fp16 as
  of iOS 14 / macOS 11), and the GPU, which uses fp16 storage with fp32 accumulation unless
  `allowLowPrecisionAccumulationOnGPU` is set.
- **A single fp32 literal in Apple's own runtime is enough to break residency.** The zoo's
  authoring rules: a Python float literal (`1.0`) creates an f32 buffer and breaks ANE residency;
  `.float()` is a no-op on the ANE because MPSGraph drops the cast. To get fp32 accumulation you
  must use an op the hardware accumulates in fp32 (the conv engine, the LayerNorm kernel).
- **Some reductions must stay fp32, and the LFM2.5-VL port is the concrete counter-example.**
  shershah1024/lfm2.5-vl-ane runs the whole 450M vision-language model on the ANE, but reports:
  *"the **RMSNorm reductions are kept in fp32** — true-fp16 reductions lose enough precision to
  break coordinate-precise generation (bounding boxes collapse, caption tails degrade) … (a handful
  of cheap ops on CPU)"*. Its reported residency is vision 100%, language ~92% **of cost**, and the
  ~8% that is not on the ANE is attributed to exactly those fp32 reductions. This is the same
  fp32-ism rule the zoo learned from the other direction (the `[x,-x]` LayerNorm trick used to
  make RMSNorm accumulate in fp32 while staying on the ANE).
- **At the surface, dtype is a choice.** maderix allocates fp32-sized surfaces in the PoC and fp16
  in the training kernels; the README claims fp16 direct I/O is ~37% faster. ANE-LM converts
  BF16 safetensors weights to fp16 once (`convert` subcommand: "BF16 -> FP16, speeds up subsequent
  loads") and stores fp16 on every surface. maderix also reports the *inverse* trap in
  neural-engine's `other.md` — an mlmodel storing 16-bit weights was observed to be *slower* than
  one storing 32-bit weights, which the author flags as not understood.

### What the memory does

Two memory facts constrain the boundary as much as dtype does, both from libane's hardware
introspection doc:

- An activation at `[1, C, 1, S]` uses **`C × S × 2` bytes**, and the ANE holds at least input and
  output simultaneously, so the minimum on-chip requirement per dispatch is `2 × C × S × 2` bytes.
  The doc's approximate SRAM table is M1 ~8 MB, M2 ~16 MB, M3 ~32 MB, M4 ~48 MB — with the explicit
  warning that `max_seq` and `max_channels` are *independent per-dimension caps*, not simultaneous
  limits; `max_seq × max_channels` would need gigabytes.
- If intermediates spill to DRAM, expect roughly a **30% throughput penalty**; `libane_mil_sram_spill()`
  detects it and the doc says a spill cannot be resolved at runtime.

Our own EXP-005 measurement adds a related negative result: clearing the file cache before a run
made things *worse*, and correctly so — **the ANE reads weights from unified memory either way, so
file residency is irrelevant**.

---

## 5. Batching and the request lifecycle

### The request lifecycle is `compile → load → request → evaluate → unload`

Compilation is the expensive, one-time part; the request is a reusable object bound to fixed
surfaces; evaluation is the steady-state call. Three things break the simple picture.

**(a) The per-process compile limit and the exec() restart.** Both maderix READMEs state it:

> **~119 compile limit** — ANE compiler leaks resources; worked around via `exec()` restart with checkpoint.
> **exec() restart**: Workaround for ANE ~119 compile limit per process

The hardened implementation is in the *static* pipeline, `train_large.m`, which bakes weights as
constants and therefore must recompile whenever weights change. It keeps a global counter and a
self-imposed ceiling of 100 rather than 119:

```objc
// Source: maderix/ANE, training/stories_config.h
#define ACCUM_STEPS 10
#define MAX_COMPILES 100
```

```c
// Source: maderix/ANE, training/train_large.m
// Check compile budget
if (g_compile_count + TOTAL_WEIGHT_KERNELS > MAX_COMPILES) {
    for (int L=0; L<NLAYERS; L++) { free_layer_kernels(&kern[L]); free_kern(sdpaBwd2[L]); }
    double wall = tb_ms(mach_absolute_time() - t_wall_start);
    save_checkpoint(ckpt_path, step, total_steps, lr, last_loss, ...);
    printf("[exec() restart step %d, %d compiles, loss=%.4f]\n", step, g_compile_count, last_loss);
    fflush(stdout);
    execl(argv[0], argv[0], "--resume", "--ckpt", ckpt_path, "--data", data_path, NULL);
    perror("execl"); return 1;
}
```

with the counter incremented inside the shared compile helper:

```c
// Source: maderix/ANE, training/training_dynamic/io.h
__sync_fetch_and_add(&g_compile_count, 1);
```

The checkpoint carries `magic = 0x424C5A54`, the step, and the full model + Adam state under the
same `--ckpt` path, so the restart is lossless. The static pipeline's own accounting: 60
weight-bearing compiles per batch (5 kernels × 12 layers), restarted every 10 accumulated steps;
7.6 s of compile per restart in the baseline, 9.6 s for the ANE-extras variant with 86 kernels.
The load/dynamic pipeline avoids the problem entirely by *not* recompiling: 10 kernels once,
~0.4 s one-time compile, "No exec() restart, no compile limit issues".

**(b) Batching changes the submission count, not the program.** AtomGradient's batch-prefill work
measures what happens when you stop dispatching one token at a time:

| Model | Sequential (1 tok/dispatch) | Batch (32 tok/dispatch) | Speedup |
| --- | ---: | ---: | ---: |
| Qwen3.5-0.8B | 23.7 tok/s | 268.0 tok/s | **11.3×** |
| Qwen3.5-2B | 23.7 tok/s | 172.7 tok/s | **7.3×** |

with ANE prefill power at **0.22 W of GPU power** (282× below a GPU prefill) and total power during
concurrent ANE-prefill + GPU-decode of ~15.8 W vs ~76 W all-GPU. State transfer between the ANE
prefill and the GPU decode is quoted at **<30 ms**, which is what makes turn-2+ TTFT 27 ms.

**(c) Submission count is the real lever in the other direction.** The zoo's Instruments traces of
an ANE-authored encoder (measured by Rahul Rachuri) show **25 ANE submissions per forward pass
against 1 for the Core ML conversion of the same network** — ANE busy 147.6 ms vs 150.4 ms, within
2%, but 28.7% idle against 0.4%. The zoo's own conclusion: *"The submission count is the region
count"*, and the ~2.3 ms IOSurface round trip is paid 25 times instead of once.

**(d) Multi-procedure programs amortise the lifecycle.** Rather than compiling N programs,
ane-infer compiles one with N procedures and dispatches by `procedureIndex` (see section 2). Its
own framing of the alternative is worth quoting because it names the leak directly:
`doEvaluateDirectWithModel:` "Bypasses ANE daemon, 10% faster eval".

---

## 6. Minimal end-to-end recipe: from a compiled program to numbers

This is the shortest path that a competent engineer can actually run. It is the union of
maderix's `inmem_basic.m` (which is a complete, single-file, working program) and ane-infer's
bridge (which is the same flow factored into a library). Assume you have a Core ML model compiled
to a `.mlmodelc` directory containing `model.mil` and `weights/`.

```objc
// Step 0. Runtime setup — Source: maderix/ANE, inmem_basic.m
#import <Foundation/Foundation.h>
#import <CoreML/CoreML.h>
#import <objc/runtime.h>
#import <objc/message.h>
#import <dlfcn.h>
#import <mach/mach_time.h>
#import <IOSurface/IOSurface.h>

dlopen("/System/Library/PrivateFrameworks/AppleNeuralEngine.framework/AppleNeuralEngine", RTLD_NOW);
Class Desc = NSClassFromString(@"_ANEInMemoryModelDescriptor");
Class IMM  = NSClassFromString(@"_ANEInMemoryModel");
Class AR   = NSClassFromString(@"_ANERequest");
Class AIO  = NSClassFromString(@"_ANEIOSurfaceObject");
```

**1. Get MIL text and the weight blob.** Compile the Core ML model, then read `model.mil` and
`weights/weight.bin` out of the compiled directory (maderix `inmem_basic.m`).

**2. Build the descriptor.**

```objc
// Source: maderix/ANE, inmem_basic.m
NSDictionary *wdict = @{
    @"@model_path/weights/weight.bin": @{@"offset": @64, @"data": weightBlob}
};
id desc = ((id(*)(Class,SEL,id,id,id))objc_msgSend)(
    Desc, @selector(modelWithMILText:weights:optionsPlist:), milData, wdict, nil);
id model = ((id(*)(Class,SEL,id))objc_msgSend)(IMM, @selector(inMemoryModelWithDescriptor:), desc);
```

**3. Write MIL and weights into `$TMPDIR/<hexStringIdentifier>/`** — `model.mil` and
`weights/weight.bin` respectively. The compile step fails without this.

**4. Compile and load (QoS 21).** `compileWithQoS:21:options:@{}:error:&e`, then
`loadWithQoS:21:options:@{}:error:&e`. On load failure, ane-infer retries once after 100 ms.

**5. Create one input and one output IOSurface** sized to the tensors' byte counts, using the
dictionary from section 1, and wrap each in `_ANEIOSurfaceObject.objectWithIOSurface:`.

**6. Build the request once.**

```objc
// Source: maderix/ANE, inmem_basic.m
id req = ((id(*)(Class,SEL,id,id,id,id,id,id,id))objc_msgSend)(AR,
    @selector(requestWithInputs:inputIndices:outputs:outputIndices:weightsBuffer:perfStats:procedureIndex:),
    @[wIn], @[@0], @[wOut], @[@0], nil, nil, @0);
```

**7. Write the input.** Convert to fp16, then lock/memcpy/unlock the input surface. In C, using
the NEON helper if you are in Objective-C (maderix `io.h`), or the scalar path if you are in C++
(ANE-LM `ane_matvec` writes one value per channel row at `c * ANE_SPATIAL`).

**8. Evaluate.**

```objc
// Source: maderix/ANE, inmem_basic.m
BOOL ok = ((BOOL(*)(id,SEL,unsigned int,id,id,NSError**))objc_msgSend)(
    model, @selector(evaluateWithQoS:options:request:error:), 21, @{}, req, &e);
```

Optional, per ane-infer: keep a shared `_ANEClient` from
`[[_ANEClient alloc] initWithRestrictedAccessAllowed:YES]` and call
`doEvaluateDirectWithModel:options:request:qos:error:` for ~10% lower latency.

**9. Read the output surface** with `IOSurfaceLock(out, kIOSurfaceLockReadOnly, NULL)`, convert
fp16 → fp32, `IOSurfaceUnlock`.

**10. Convert and check.** maderix's PoC computes `2 * ch * ch * sp / 1e9 / ms` TFLOPS and prints
the value, which is how you know it ran rather than silently no-op'ing.

**11. Tear down.** `unloadWithQoS:21:error:&e`, `CFRelease` both surfaces, remove the temp dir.

**Gotchas that will actually bite, in order of likelihood:** the temp directory does not exist or
is missing `weights/` (step 3); the surface is smaller than the tensor the MIL declares (silent
garbage); the request's input index array does not match the MIL's parameter order; the compile
counter has exceeded the per-process limit and `loadWithQoS:` starts failing (restart the process
with a checkpoint); and the MIL contains an fp32 literal that silently pushed the graph off the
ANE.

---

## Records

```jsonl
{"id":"RUNTIME-001","claim":"IOSurface is a public Apple framework buffer type (IOSurface.framework) that every direct-ANE project uses to pass tensors to the Neural Engine, while the ANE-side wrapper classes are private.","kind":"definition","confidence":"documented","source":"https://raw.githubusercontent.com/maderix/ANE/main/inmem_basic.m","source_type":"primary","retrieved":"2026-09-23","topic":["iosurface","memory","runtime"],"entities":["IOSurface","AppleNeuralEngine.framework"],"contested":false,"split":"holdout"}
{"id":"RUNTIME-002","claim":"The IOSurface configuration used by every surveyed ANE project sets width to the byte count, height to 1, bytesPerElement to 1, bytesPerRow to the byte count, allocSize to the byte count and pixelFormat to 0.","kind":"procedure","confidence":"documented","source":"https://raw.githubusercontent.com/thebasedcapital/ane-infer/main/crates/ane-bridge/objc/ane_runtime.m","source_type":"primary","retrieved":"2026-09-23","topic":["iosurface","allocation"],"entities":["IOSurfaceCreate","ane-infer","maderix/ANE","ANE-LM"],"evidence":"kIOSurfaceWidth:@(bytes), kIOSurfaceHeight:@1, kIOSurfaceBytesPerElement:@1, kIOSurfaceBytesPerRow:@(bytes), kIOSurfaceAllocSize:@(bytes), kIOSurfacePixelFormat:@0","contested":false,"split":"train"}
{"id":"RUNTIME-003","claim":"An ANE request binds IOSurface-backed buffers by index instead of raw pointers, so input and output tensors must be allocated as IOSurfaces before a request can be built.","kind":"fact","confidence":"documented","source":"https://raw.githubusercontent.com/thebasedcapital/ane-infer/main/crates/ane-bridge/objc/ane_runtime.m","source_type":"primary","retrieved":"2026-09-23","topic":["iosurface","binding","runtime"],"entities":["_ANERequest","_ANEIOSurfaceObject"],"contested":false,"split":"train"}
{"id":"RUNTIME-004","claim":"The private class _ANEIOSurfaceObject wraps a single IOSurfaceRef into a request buffer through the class method +objectWithIOSurface:.","kind":"fact","confidence":"documented","source":"https://raw.githubusercontent.com/maderix/ANE/main/inmem_basic.m","source_type":"primary","retrieved":"2026-09-23","topic":["private-api","iosurface"],"entities":["_ANEIOSurfaceObject"],"contested":false,"split":"train"}
{"id":"RUNTIME-005","claim":"The private class _ANERequest is constructed with +requestWithInputs:inputIndices:outputs:outputIndices:weightsBuffer:perfStats:procedureIndex:, taking parallel arrays of buffer objects and their indices plus a procedure index.","kind":"procedure","confidence":"documented","source":"https://raw.githubusercontent.com/maderix/ANE/main/bridge/ane_bridge.m","source_type":"primary","retrieved":"2026-09-23","topic":["private-api","runtime","binding"],"entities":["_ANERequest"],"contested":false,"split":"train"}
{"id":"RUNTIME-006","claim":"ANE projects build the _ANERequest object once per compiled kernel and reuse it for every subsequent evaluation rather than rebuilding it per call.","kind":"procedure","confidence":"documented","source":"https://raw.githubusercontent.com/thebasedcapital/ane-infer/main/crates/ane-bridge/objc/ane_runtime.m","source_type":"primary","retrieved":"2026-09-23","topic":["runtime","performance"],"entities":["_ANERequest","ane-infer"],"evidence":"struct field comment: // _ANERequest (reused across evals)","contested":false,"split":"train"}
{"id":"RUNTIME-007","claim":"Using the _ANEIOSurfaceOutputSets factory outputSetsWithBuffers: causes ANEProgramChainingPrepare() to fail with error 15, whereas objectWithstatsSurRef:outputBuffer: succeeds.","kind":"gotcha","confidence":"claimed","source":"https://raw.githubusercontent.com/thebasedcapital/ane-infer/main/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["private-api","iosurface","chaining"],"entities":["_ANEIOSurfaceOutputSets"],"evidence":"Before: outputSetsWithBuffers:@[buf_out] -> error 15; After: objectWithstatsSurRef:ioStats outputBuffer:@[buf_out] -> SUCCESS","caveat":"Reported by one project (ane-infer) as its own probe result; not independently reproduced in the sources surveyed","contested":false,"split":"train"}
{"id":"RUNTIME-008","claim":"With the corrected _ANEIOSurfaceOutputSets factory, both prepareChainingWithModel: and the direct doPrepareChainingWithModel: succeed, while the buffersReady step remains blocked.","kind":"fact","confidence":"claimed","source":"https://raw.githubusercontent.com/thebasedcapital/ane-infer/main/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["private-api","chaining"],"entities":["_ANEIOSurfaceOutputSets","_ANEDaemonConnection"],"caveat":"Single-project report as of ane-infer's README","contested":false,"split":"train"}
{"id":"RUNTIME-009","claim":"Calling doEvaluateDirectWithModel:options:request:qos:error: on a shared _ANEClient obtained with initWithRestrictedAccessAllowed:YES bypasses the ANE daemon and is reported to evaluate about 10% faster.","kind":"measurement","confidence":"claimed","source":"https://raw.githubusercontent.com/thebasedcapital/ane-infer/main/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["runtime","performance","private-api"],"entities":["_ANEClient","ane-infer"],"caveat":"10% figure is the project's own claim without a published harness","contested":false,"split":"train"}
{"id":"RUNTIME-010","claim":"An in-memory ANE program is created by calling +modelWithMILText:weights:optionsPlist: on _ANEInMemoryModelDescriptor and then +inMemoryModelWithDescriptor: on _ANEInMemoryModel.","kind":"procedure","confidence":"documented","source":"https://raw.githubusercontent.com/maderix/ANE/main/bridge/ane_bridge.m","source_type":"primary","retrieved":"2026-09-23","topic":["compile","binding"],"entities":["_ANEInMemoryModelDescriptor","_ANEInMemoryModel"],"contested":false,"split":"train"}
{"id":"RUNTIME-011","claim":"Weights are supplied to the ANE descriptor as a dictionary whose keys are virtual MIL paths of the form @model_path/weights/<name>.bin and whose values are dictionaries with an offset and a data blob.","kind":"procedure","confidence":"documented","source":"https://raw.githubusercontent.com/maderix/ANE/main/bridge/ane_bridge.m","source_type":"primary","retrieved":"2026-09-23","topic":["weights","compile"],"entities":["_ANEInMemoryModelDescriptor","MIL"],"contested":false,"split":"train"}
{"id":"RUNTIME-012","claim":"Before compilation the MIL text and every weight blob must be written as real files under $TMPDIR/<hexStringIdentifier>/, with the MIL at model.mil and each weight at its @model_path-relative path.","kind":"procedure","confidence":"documented","source":"https://raw.githubusercontent.com/maderix/ANE/main/inmem_basic.m","source_type":"primary","retrieved":"2026-09-23","topic":["compile","filesystem"],"entities":["_ANEInMemoryModel.hexStringIdentifier"],"evidence":"createDirectoryAtPath:<tmpDir>/weights, writeToFile:<tmpDir>/model.mil, writeToFile:<tmpDir>/weights/weight.bin","contested":false,"split":"train"}
{"id":"RUNTIME-013","claim":"ANE weight blobs use a 128-byte header carrying magic bytes 0xEF 0xBE 0xAD 0xDE at offset 64, the fp16 payload size at offset 72 and the payload start offset 128 at offset 80.","kind":"definition","confidence":"documented","source":"https://raw.githubusercontent.com/maderix/ANE/main/training/training_dynamic/io.h","source_type":"primary","retrieved":"2026-09-23","topic":["weights","format"],"entities":["ANE weight blob"],"contested":false,"split":"holdout"}
{"id":"RUNTIME-014","claim":"ANE compilation and loading are invoked through compileWithQoS:options:error: and loadWithQoS:options:error: with a QoS value of 21 and an empty options dictionary.","kind":"procedure","confidence":"documented","source":"https://raw.githubusercontent.com/maderix/ANE/main/inmem_basic.m","source_type":"primary","retrieved":"2026-09-23","topic":["compile","runtime"],"entities":["compileWithQoS","loadWithQoS"],"contested":false,"split":"train"}
{"id":"RUNTIME-015","claim":"maderix's ANE bridge retries a failed loadWithQoS: once after a 100 ms sleep, commented as waiting for ANE slot reclamation.","kind":"procedure","confidence":"documented","source":"https://raw.githubusercontent.com/maderix/ANE/main/bridge/ane_bridge.m","source_type":"primary","retrieved":"2026-09-23","topic":["compile","gotcha"],"entities":["loadWithQoS","ane_bridge.m"],"evidence":"usleep(100000); // 100ms","contested":false,"split":"train"}
{"id":"RUNTIME-016","claim":"ANE-LM keeps a persistent ANE compile cache by writing a marker file at $HOME/Library/Caches/ane_lm/compiled_markers/<hexStringIdentifier>.ok after a successful compile, and skips compilation when the marker already exists.","kind":"procedure","confidence":"documented","source":"https://raw.githubusercontent.com/johnmai-dev/ANE-LM/main/core/ane_runtime.cpp","source_type":"primary","retrieved":"2026-09-23","topic":["compile","caching"],"entities":["ANE-LM","hexStringIdentifier"],"contested":false,"split":"train"}
{"id":"RUNTIME-017","claim":"ANE-LM exposes a --no-ane-cache flag that disables its persistent ANE compile cache.","kind":"fact","confidence":"documented","source":"https://raw.githubusercontent.com/johnmai-dev/ANE-LM/main/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["compile","caching"],"entities":["ANE-LM"],"contested":false,"split":"train"}
{"id":"RUNTIME-018","claim":"Steady-state ANE execution is performed with evaluateWithQoS:options:request:error: passing the prebuilt request object and a QoS value of 21.","kind":"procedure","confidence":"documented","source":"https://raw.githubusercontent.com/maderix/ANE/main/training/training_dynamic/io.h","source_type":"primary","retrieved":"2026-09-23","topic":["runtime"],"entities":["evaluateWithQoS"],"contested":false,"split":"train"}
{"id":"RUNTIME-019","claim":"An ANE kernel is torn down by calling unloadWithQoS:error:, releasing its IOSurfaces with CFRelease and removing its temporary compile directory.","kind":"procedure","confidence":"documented","source":"https://raw.githubusercontent.com/maderix/ANE/main/bridge/ane_bridge.m","source_type":"primary","retrieved":"2026-09-23","topic":["runtime","cleanup"],"entities":["unloadWithQoS"],"contested":false,"split":"train"}
{"id":"RUNTIME-020","claim":"Host access to ANE I/O buffers is done by IOSurfaceLock, memcpy against IOSurfaceGetBaseAddress and IOSurfaceUnlock, with kIOSurfaceLockReadOnly used for output reads.","kind":"procedure","confidence":"documented","source":"https://raw.githubusercontent.com/thebasedcapital/ane-infer/main/crates/ane-bridge/objc/ane_runtime.m","source_type":"primary","retrieved":"2026-09-23","topic":["iosurface","io"],"entities":["IOSurfaceLock","IOSurfaceGetBaseAddress"],"contested":false,"split":"holdout"}
{"id":"RUNTIME-021","claim":"The ANE expects activations in the [1, C, 1, S] layout, known as BC1S, with batch and height fixed at 1.","kind":"definition","confidence":"documented","source":"https://raw.githubusercontent.com/AmiraniLabs/libane/main/docs/graph-ir.md","source_type":"primary","retrieved":"2026-09-23","topic":["layout","boundary"],"entities":["ANE","BC1S","libane"],"contested":false,"split":"train"}
{"id":"RUNTIME-022","claim":"In the ANE layout a matrix multiplication A[M,K] times B[K,N] is expressed as A of shape [1,K,1,M], B (weights) of shape [1,N,1,K] and output of shape [1,N,1,M].","kind":"definition","confidence":"documented","source":"https://raw.githubusercontent.com/AmiraniLabs/libane/main/docs/graph-ir.md","source_type":"primary","retrieved":"2026-09-23","topic":["layout","matmul"],"entities":["libane","conv1x1"],"contested":false,"split":"train"}
{"id":"RUNTIME-023","claim":"libane implements every matmul as a 1x1 convolution and claims roughly 3x the throughput of MIL's native matmul op on ANE.","kind":"measurement","confidence":"claimed","source":"https://raw.githubusercontent.com/AmiraniLabs/libane/main/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["matmul","performance"],"entities":["libane","MIL"],"evidence":"README links the 3x figure to arXiv 2603.06728","caveat":"Throughput comparison is the project's own claim, sourced to an arXiv paper not read for this file","contested":false,"split":"train"}
{"id":"RUNTIME-024","claim":"ANE-LM defines ANE_SPATIAL = 32 as the minimum spatial dimension the hardware requires and pads its matmul input tensors to that width.","kind":"fact","confidence":"documented","source":"https://raw.githubusercontent.com/johnmai-dev/ANE-LM/main/core/ane_runtime.h","source_type":"primary","retrieved":"2026-09-23","topic":["layout","shape-limits"],"entities":["ANE-LM"],"evidence":"constexpr int ANE_SPATIAL = 32; // ANE minimum spatial dimension required by hardware","contested":false,"split":"train"}
{"id":"RUNTIME-025","claim":"libane's graph API requires the spatial dimension S to be a multiple of 16 and requires S to be non-zero.","kind":"gotcha","confidence":"documented","source":"https://raw.githubusercontent.com/AmiraniLabs/libane/main/docs/graph-ir.md","source_type":"primary","retrieved":"2026-09-23","topic":["shape-limits","layout"],"entities":["libane","ANE"],"evidence":"seq_alignment is always 16","contested":false,"split":"train"}
{"id":"RUNTIME-026","claim":"libane's graph API enforces a channel cap of C less than or equal to 16384 and requires raw MIL emission for larger channel counts such as vocabulary projections.","kind":"gotcha","confidence":"documented","source":"https://raw.githubusercontent.com/AmiraniLabs/libane/main/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["shape-limits"],"entities":["libane"],"contested":false,"split":"train"}
{"id":"RUNTIME-027","claim":"An ANE activation buffer of shape [1,C,1,S] costs C times S times 2 bytes of on-chip SRAM and the ANE holds at least input and output simultaneously, so a dispatch needs at least 2*C*S*2 bytes.","kind":"fact","confidence":"documented","source":"https://raw.githubusercontent.com/AmiraniLabs/libane/main/docs/hardware-introspection.md","source_type":"primary","retrieved":"2026-09-23","topic":["sram","memory"],"entities":["libane","ANE"],"contested":false,"split":"holdout"}
{"id":"RUNTIME-028","claim":"Approximate ANE SRAM is about 8 MB on M1, 16 MB on M2, 32 MB on M3 and 48 MB on M4, and the max_seq and max_channels limits are independent per-dimension caps rather than simultaneous limits.","kind":"fact","confidence":"documented","source":"https://raw.githubusercontent.com/AmiraniLabs/libane/main/docs/hardware-introspection.md","source_type":"primary","retrieved":"2026-09-23","topic":["sram","memory"],"entities":["M1","M2","M3","M4","libane"],"caveat":"Figures are libane's approximations, not Apple specifications","contested":false,"split":"train"}
{"id":"RUNTIME-029","claim":"When intermediate activations spill out of ANE SRAM to DRAM the throughput penalty is roughly 30 percent and the spill cannot be fixed at runtime.","kind":"gotcha","confidence":"documented","source":"https://raw.githubusercontent.com/AmiraniLabs/libane/main/docs/hardware-introspection.md","source_type":"primary","retrieved":"2026-09-23","topic":["sram","performance"],"entities":["libane"],"contested":false,"split":"train"}
{"id":"RUNTIME-030","claim":"libane reads the ANE architecture string and core counts from the private _ANEDeviceInfo class, reporting h11g for A14/M1, h12g for A15/M2, h13g for A16, h14g for A17/M3 early, h15g for M3 and h16g for M4.","kind":"fact","confidence":"documented","source":"https://raw.githubusercontent.com/AmiraniLabs/libane/main/docs/hardware-introspection.md","source_type":"primary","retrieved":"2026-09-23","topic":["device-introspection"],"entities":["_ANEDeviceInfo","libane","h15g","h16g"],"caveat":"Strings are firmware-reported and new chips may report values not in the list","contested":false,"split":"train"}
{"id":"RUNTIME-031","claim":"libane's graph API supports fp16 only and offers no int8 or int4 quantization for weights or activations.","kind":"fact","confidence":"documented","source":"https://raw.githubusercontent.com/AmiraniLabs/libane/main/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["precision"],"entities":["libane"],"contested":false,"split":"holdout"}
{"id":"RUNTIME-032","claim":"maderix reports that fp16 direct I/O on IOSurfaces is about 37 percent faster than fp32 direct I/O on the ANE.","kind":"measurement","confidence":"claimed","source":"https://raw.githubusercontent.com/maderix/ANE/main/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["precision","io","performance"],"entities":["maderix/ANE","IOSurface"],"caveat":"Stated in the project README without a published benchmark procedure","contested":false,"split":"train"}
{"id":"RUNTIME-033","claim":"Both fp32-sized and fp16-sized IOSurfaces are accepted as ANE I/O buffers: maderix's proof-of-concept allocates ch*sp*4 bytes while the training kernels store _Float16 on the surface.","kind":"fact","confidence":"documented","source":"https://raw.githubusercontent.com/maderix/ANE/main/inmem_basic.m","source_type":"primary","retrieved":"2026-09-23","topic":["precision","io"],"entities":["maderix/ANE","IOSurface"],"evidence":"inmem_basic.m: NSUInteger bytes = ch * sp * 4; io.h: write via cvt_f32_f16 into _Float16 buffers","contested":false,"split":"train"}
{"id":"RUNTIME-034","claim":"ANE-LM converts BF16 safetensors weights to fp16 once via a convert subcommand before staging them into ANE weight blobs.","kind":"procedure","confidence":"documented","source":"https://raw.githubusercontent.com/johnmai-dev/ANE-LM/main/core/ane_runtime.cpp","source_type":"primary","retrieved":"2026-09-23","topic":["precision","weights"],"entities":["ANE-LM","bf16_to_f16_vec"],"contested":false,"split":"train"}
{"id":"RUNTIME-035","claim":"The ANE appears to use float16 for everything, so activations above about 1e2 or below about 1e-4 lose precision and very small values may become zero.","kind":"fact","confidence":"claimed","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/16-bit.md","source_type":"secondary","retrieved":"2026-09-23","topic":["precision"],"entities":["ANE"],"caveat":"Stated as an observation ('appears to') in community documentation, not a measured hardware study","contested":false,"split":"train"}
{"id":"RUNTIME-036","claim":"Core ML uses float32 for weights, intermediates and computation on the CPU, and float16 for GPU weights and intermediates with float32 accumulations unless allowLowPrecisionAccumulationOnGPU is enabled.","kind":"fact","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/16-bit.md","source_type":"secondary","retrieved":"2026-09-23","topic":["precision"],"entities":["Core ML","CPU","GPU"],"contested":false,"split":"train"}
{"id":"RUNTIME-037","claim":"A single fp32 literal such as a Python float 1.0 creates an f32 buffer in the Core AI authoring path and breaks ANE residency, and calling .float() is a no-op on the ANE because the cast is dropped.","kind":"gotcha","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/compute-units-and-authoring.md","source_type":"secondary","retrieved":"2026-09-23","topic":["precision","boundary","gotcha"],"entities":["Core AI","ANE"],"caveat":"Recorded against Apple's ANE authoring rules; the same effect on a hand-written MIL program is not verified here","contested":false,"split":"train"}
{"id":"RUNTIME-038","claim":"On the ANE, projections expressed as 1x1 Conv2d rather than nn.Linear are accumulated in fp32 by the conv engine, which is the standard fix for fp16 drift across many layers.","kind":"fact","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/compute-units-and-authoring.md","source_type":"secondary","retrieved":"2026-09-23","topic":["precision","layouts"],"entities":["ANE","Conv2d"],"contested":false,"split":"train"}
{"id":"RUNTIME-039","claim":"The LFM2.5-VL ANE port keeps RMSNorm reductions in fp32 because true-fp16 reductions lose enough precision to break coordinate-precise generation, collapsing predicted bounding boxes.","kind":"measurement","confidence":"measured","source":"https://raw.githubusercontent.com/shershah1024/lfm2.5-vl-ane/master/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["precision","boundary","reductions"],"entities":["LFM2.5-VL-450M","ANE","RMSNorm"],"evidence":"README reports bounding boxes collapse and caption tails degrade with fp16 reductions","caveat":"Reported for one 450M vision-language model; the fp32 ops run on CPU, not on the ANE","contested":false,"split":"train"}
{"id":"RUNTIME-040","claim":"The LFM2.5-VL ANE port reports 100 percent ANE residency for the vision tower and about 92 percent of cost for the language stack, with the remaining cost attributed to fp32 RMSNorm reductions.","kind":"measurement","confidence":"measured","source":"https://raw.githubusercontent.com/shershah1024/lfm2.5-vl-ane/master/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["residency","precision"],"entities":["LFM2.5-VL-450M","ANE"],"evidence":"Neural Engine residency: vision 100%; language ~92% of cost (RMSNorm reductions in fp32)","caveat":"'Residency' here is reported as share of cost, not an interval count","contested":false,"split":"train"}
{"id":"RUNTIME-041","claim":"The ANE KV cache pattern in Apple's iOS authoring rules is readonly functional I/O: the model concatenates past and new K/V, returns the new values, and the host writes the cache, with the sequence dimension on dimension 4.","kind":"definition","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/compute-units-and-authoring.md","source_type":"secondary","retrieved":"2026-09-23","topic":["kv-cache","memory","boundary"],"entities":["ANE","KV cache"],"caveat":"Apple's own KVCacheHandler uses a stateful write instead, which the project reports fails to lower on device","contested":false,"split":"train"}
{"id":"RUNTIME-042","claim":"maderix reports that multi-input ANE requests fail with error 0x1d, forcing projects to pack multiple inputs into the spatial dimension instead.","kind":"gotcha","confidence":"claimed","source":"https://raw.githubusercontent.com/maderix/ANE/main/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["single-input","gotcha"],"entities":["maderix/ANE","_ANERequest"],"evidence":"Limitations: 'multi-input ANE requests cause 0x1d error; inputs packed into spatial dimension instead'","caveat":"Contested: thebasedcapital/ane-infer and ANE-LM both construct request arrays sized n_inputs, though neither documents a working multi-input dispatch","contested":true,"split":"holdout"}
{"id":"RUNTIME-043","claim":"ane-infer and ANE-LM build their _ANERequest input and output arrays programmatically from an n_inputs parameter rather than hard-coding a single input buffer.","kind":"fact","confidence":"documented","source":"https://raw.githubusercontent.com/thebasedcapital/ane-infer/main/crates/ane-bridge/objc/ane_runtime.m","source_type":"primary","retrieved":"2026-09-23","topic":["single-input","binding"],"entities":["ane-infer","ANE-LM","_ANERequest"],"caveat":"Contested against maderix's claim that any multi-input request returns error 0x1d; array-capable code is not evidence that more than one input was exercised","contested":true,"split":"train"}
{"id":"RUNTIME-044","claim":"maderix packs activations and weights into one spatial dimension: the sdpaFwd kernel input is [1, DIM, 1, SEQ+Q_DIM+KV_DIM+KV_DIM] with the activations followed by three weight matrices.","kind":"procedure","confidence":"documented","source":"https://raw.githubusercontent.com/maderix/ANE/main/training/training_dynamic/io.h","source_type":"primary","retrieved":"2026-09-23","topic":["single-input","layout","weights"],"entities":["maderix/ANE","sdpaFwd"],"evidence":"#define SDPA_FWD_SP (SEQ + Q_DIM + KV_DIM + KV_DIM)","contested":false,"split":"train"}
{"id":"RUNTIME-045","claim":"Because weights travel inside the IOSurface spatial dimension, maderix's dynamic pipeline compiles ten kernels once at startup and changes weights without recompilation.","kind":"procedure","confidence":"documented","source":"https://raw.githubusercontent.com/maderix/ANE/main/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["weights","compile","runtime"],"entities":["maderix/ANE","training_dynamic"],"evidence":"10 shared kernels, ~0.4 s one-time compile, 'No exec() restart, no compile limit issues'","contested":false,"split":"train"}
{"id":"RUNTIME-046","claim":"maderix's static training pipeline bakes weights into MIL constants and therefore recompiles 5 weight-bearing kernels per layer (60 for 12 layers) every 10 accumulated steps.","kind":"fact","confidence":"documented","source":"https://raw.githubusercontent.com/maderix/ANE/main/training/stories_config.h","source_type":"primary","retrieved":"2026-09-23","topic":["compile","runtime"],"entities":["train_large","Stories110M"],"evidence":"#define KERNELS_PER_LAYER 5, #define TOTAL_WEIGHT_KERNELS (KERNELS_PER_LAYER * NLAYERS), #define ACCUM_STEPS 10","contested":false,"split":"train"}
{"id":"RUNTIME-047","claim":"The ANE compiler leaks resources and a process can perform only roughly 119 ANE compiles before it must be restarted.","kind":"gotcha","confidence":"claimed","source":"https://raw.githubusercontent.com/maderix/ANE/main/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["compile","gotcha"],"entities":["maderix/ANE","ANECompiler"],"evidence":"Limitations: '~119 compile limit - ANE compiler leaks resources; worked around via exec() restart with checkpoint'","caveat":"The number is approximate and undocumented by Apple; maderix's own static pipeline caps itself at 100 for margin","contested":false,"split":"train"}
{"id":"RUNTIME-048","claim":"maderix's static pipeline guards the compile budget with a self-imposed MAX_COMPILES of 100 and restarts the process with execl(argv[0], '--resume', '--ckpt', ...) when the next batch would exceed it.","kind":"procedure","confidence":"documented","source":"https://raw.githubusercontent.com/maderix/ANE/main/training/train_large.m","source_type":"primary","retrieved":"2026-09-23","topic":["compile","gotcha","lifecycle"],"entities":["train_large","execl"],"evidence":"if (g_compile_count + TOTAL_WEIGHT_KERNELS > MAX_COMPILES) { ... execl(argv[0], argv[0], \"--resume\", \"--ckpt\", ckpt_path, \"--data\", data_path, NULL); }","contested":false,"split":"train"}
{"id":"RUNTIME-049","claim":"The exec restart is lossless because the model weights, Adam optimizer state and step counter are written to a checkpoint with magic 0x424C5A54 before the restart and reloaded afterwards.","kind":"procedure","confidence":"documented","source":"https://raw.githubusercontent.com/maderix/ANE/main/training/train_large.m","source_type":"primary","retrieved":"2026-09-23","topic":["checkpoint","lifecycle"],"entities":["train_large","exec restart"],"contested":false,"split":"train"}
{"id":"RUNTIME-050","claim":"One compiled ANE program can contain several procedures dispatched by procedureIndex, and ane-infer enumerates them via model -> modelAttributes -> ANEFModelDescription -> ANEFModelProcedures, pre-building one request per procedure.","kind":"procedure","confidence":"documented","source":"https://raw.githubusercontent.com/thebasedcapital/ane-infer/main/crates/ane-bridge/objc/ane_runtime.m","source_type":"primary","retrieved":"2026-09-23","topic":["multi-procedure","runtime","binding"],"entities":["_ANERequest","_ANEInMemoryModel","ane-infer"],"contested":false,"split":"train"}
{"id":"RUNTIME-051","claim":"Batching 32 tokens per ANE dispatch instead of one raises prefill throughput from 23.7 to 268.0 tok/s for Qwen3.5-0.8B, an 11.3x speedup, and from 23.7 to 172.7 tok/s for Qwen3.5-2B, a 7.3x speedup.","kind":"measurement","confidence":"measured","source":"https://raw.githubusercontent.com/AtomGradient/hybird-batch-prefill-on-ane/main/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["batching","performance"],"entities":["Qwen3.5-0.8B","Qwen3.5-2B","M2 Ultra"],"evidence":"Sequential (1 tok/dispatch) 23.7 tok/s vs Batch (32 tok/dispatch) 268.0 / 172.7 tok/s, 74-token prompt, 10 runs averaged","caveat":"Measured on an M2 Ultra; the 2B model was run in BF16","contested":false,"split":"holdout"}
{"id":"RUNTIME-052","claim":"During batched ANE prefill the GPU draws 0.22 W, a 282x reduction versus a GPU prefill, which allows the GPU to decode a different request concurrently.","kind":"measurement","confidence":"measured","source":"https://raw.githubusercontent.com/AtomGradient/hybird-batch-prefill-on-ane/main/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["batching","power","concurrency"],"entities":["ANE","GPU","M2 Ultra"],"evidence":"GPU prefill 62.05 W vs ANE prefill 0.22 W GPU component; concurrent ANE prefill + GPU decode ~15.8 W vs ~76 W all-GPU","contested":false,"split":"train"}
{"id":"RUNTIME-053","claim":"Transferring state from an ANE prefill to a GPU decode costs under 30 ms, which brings second-turn-onward time-to-first-token to 27 ms in the hybrid pipeline.","kind":"measurement","confidence":"measured","source":"https://raw.githubusercontent.com/AtomGradient/hybird-batch-prefill-on-ane/main/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["batching","state-transfer","latency"],"entities":["AtomGradient","M2 Ultra"],"evidence":"State transfer overhead <30 ms; TTFT from turn 2+ 27 ms (3.7x faster than GPU-only)","caveat":"Numbers from one M2 Ultra harness; state is serialised through a file in the published script","contested":false,"split":"train"}
{"id":"RUNTIME-054","claim":"Core AI's ANE-authored encoder issues 25 ANE submissions per forward pass where the Core ML conversion of the same network issues 1, while ANE busy time differs by only 2 percent (147.6 ms vs 150.4 ms).","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/compute-units-and-authoring.md","source_type":"secondary","retrieved":"2026-09-23","topic":["submissions","runtime","performance"],"entities":["Core AI","Core ML","Parakeet","ANE"],"evidence":"25.0 submissions at 5.906 ms mean vs 1.0 at 150.4 ms; ANE idle 28.7% vs 0.4%","caveat":"Traces measured by Rahul Rachuri on one iPhone and republished in the zoo knowledge base","contested":false,"split":"train"}
{"id":"RUNTIME-055","claim":"An IOSurface round trip between host and ANE costs roughly 2.3 ms, which is why paying it once per submission instead of once per graph matters.","kind":"measurement","confidence":"claimed","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/compute-units-and-authoring.md","source_type":"secondary","retrieved":"2026-09-23","topic":["iosurface","latency"],"entities":["IOSurface","ANE"],"caveat":"Number is attributed to arXiv 2603.06728; the paper itself was not read for this file","contested":false,"split":"train"}
{"id":"RUNTIME-056","claim":"The ANE reads weights from unified memory regardless of file cache state, so file residency does not affect measured performance.","kind":"measurement","confidence":"measured","source":"/Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["memory","measurement"],"entities":["ANE","M4"],"evidence":"Clearing the file cache before a run made timings worse (385 -> 258 fast samples), consistent with unified-memory weight reads","contested":false,"split":"train"}
{"id":"RUNTIME-057","claim":"Unprivileged ANE activity can be observed through IOReport channels: the AMC Stats ANE read counters and the interrupt statistics subgroup ane 0 count, while the Energy Model ANE channel is frozen and must not be read as evidence of idleness.","kind":"procedure","confidence":"measured","source":"/Volumes/data/local_ai_stack/tools/enginemon/README.md","source_type":"our-own","retrieved":"2026-09-23","topic":["measurement","runtime"],"entities":["IOReport","enginemon","M4"],"evidence":"Core ML compute_units=ALL run: AMC Stats ANE DCS RD 128-171 GB and 24538-37368 ane 0 interrupts versus 0 B and 0 on idle; Energy Model ANE stayed at 0 in both","caveat":"Channel availability is SoC and OS specific; validated on macOS 27.0 / M4","contested":false,"split":"train"}
{"id":"RUNTIME-058","claim":"Core ML's computeUnits = .all only expresses a preference for the ANE and does not guarantee ANE placement, because Core ML falls back to GPU or CPU when a layer is unsupported or when the system decides otherwise.","kind":"fact","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/running-on-ane.md","source_type":"secondary","retrieved":"2026-09-23","topic":["placement","runtime"],"entities":["Core ML","MLModelConfiguration","ANE"],"contested":false,"split":"train"}
```

---

## Sources

External, with declared licences where a LICENSE file exists:

| Source | Used for | Licence (declared) |
| --- | --- | --- |
| https://github.com/maderix/ANE — `README.md`, `inmem_basic.m`, `bridge/ane_bridge.m`, `training/README.md`, `training/train_large.m`, `training/stories_config.h`, `training/training_dynamic/io.h`, `training/training_dynamic/train.m`, `training/training_dynamic/config.h` | the whole allocation/binding flow, weight blob format, single-input workaround, compile limit, exec restart | MIT (LICENSE file in repo) |
| https://github.com/johnmai-dev/ANE-LM — `README.md`, `LICENSE`, `core/ane_runtime.cpp`, `core/ane_runtime.h`, `include/ane_lm/common.h` | compile cache, fp16/BF16 conversion, ANE_SPATIAL, MIL generation | MIT (LICENSE file, "Copyright (c) 2026 John Mai") |
| https://github.com/thebasedcapital/ane-infer — `README.md`, `crates/ane-bridge/objc/ane_runtime.m` | IOSurface creation helper, request construction, `_ANEClient` direct eval, multi-procedure dispatch, `_ANEIOSurfaceOutputSets` correction | MIT (stated in README) |
| https://github.com/AmiraniLabs/libane — `README.md`, `docs/graph-ir.md`, `docs/hardware-introspection.md` | BC1S layout, S/16 and C<=16384 limits, SRAM budget and spill, device strings, fp16-only | Apache-2.0 (LICENSE file) |
| https://github.com/shershah1024/lfm2.5-vl-ane — `README.md` | fp32 RMSNorm reductions and residency figures | Code MIT; model bundle under the LFM Open License v1.0 (both declared in README) |
| https://github.com/AtomGradient/hybird-batch-prefill-on-ane — `README.md`, `LICENSE` | batched-dispatch speedups, power, state transfer | MIT (LICENSE file) |
| https://github.com/hollance/neural-engine (mirrored locally, see below) — `16-bit.md` | ANE fp16 observation, CPU/GPU precision behaviour | MIT (LICENSE file) |

Local sources:

| Path | Used for |
| --- | --- |
| /Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/compute-units-and-authoring.md | BC1S and Conv2d/fp32-accumulation rules, fp32-literal residency trap, KV-cache I/O shape, submission counts, IOSurface round-trip figure |
| /Volumes/data/local_ai_stack/results/EXP-005-ane-residency/README.md | unified-memory weight reads; file cache irrelevance |
| /Volumes/data/local_ai_stack/tools/enginemon/README.md | which IOReport channels actually report ANE activity |
| /Volumes/data/local_ai_stack/repos/neural-engine/docs/running-on-ane.md | Core ML computeUnits is a preference, not a guarantee |
| /Volumes/data/local_ai_stack/knowledge/ane/00-DESIGN.md | record schema and confidence rules |

Sources referenced but **not rendered / unreachable** during this pass, recorded rather than
silently dropped:

- **GitHub's tree API** (`https://api.github.com/repos/<owner>/<repo>/git/trees/main?recursive=1`)
  returned **HTTP 403** for both ANE-LM and maderix/ANE (rate limit), so repository file lists were
  obtained from raw file paths and the rendered tree pages instead.
- **`WHY_ANE.md`** in shershah1024/lfm2.5-vl-ane returned **404** at the `main` branch path used for
  its README; the README itself was retrieved from `master`. The decision rationale in that file was
  therefore not read.
- **arXiv 2603.06728** (the source of the ~2.3 ms IOSurface round-trip and the 3x conv1x1 matmul
  claim) was not fetched; both appear here only as cited-by-secondary claims with that caveat.
- Apple's Core ML and IOSurface **framework documentation** was not fetched; IOSurface API facts in
  this file are evidenced by the framework's use in the primary source code above, not by Apple prose.