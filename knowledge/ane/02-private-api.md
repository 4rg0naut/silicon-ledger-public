# 02 — The private `AppleNeuralEngine.framework` API

This file documents the actual private Objective-C API surface that the community has reverse-engineered
for talking to the ANE without Core ML: the classes, the real selectors and argument types, the working
load/execute sequences, and how those classes are reached from C, Rust, Python and Go. It is deliberately
explicit about which signatures are attested by a header dump or a working call site and which are
reconstructed, guessed, or simply unknown — that last part is the most valuable content here.

Scope note: this is the *framework* layer. The layer below it (the `H11ANE` IOKit kernel driver, used by
geohot's early tinygrad work) is a different interface and is described briefly in §7 only because
projects that "talk to the ANE" sometimes mean that instead.

---

## 0. How to read the confidence labels

Every non-obvious statement in this file carries one of four labels.

| Label | Meaning in this file |
|---|---|
| **MEASURED** | Someone actually ran it on ANE hardware and reported the call working, a number, or a failure. Includes selector strings lifted from working source. |
| **DOCUMENTED** | It appears in a header-level dump of the framework (`nst/iOS-Runtime-Headers`, or the generated bindings in `tmc/apple`). A dump is evidence of the interface existing, not of it working. |
| **INFERRED** | My reasoning from other evidence; no direct citation. |
| **CLAIMED** | Asserted by a project or paper without supporting evidence. Do not treat as fact. |

For signatures I use two provenance marks:

* **(call-site)** — the exact selector string appears verbatim in working code (highest confidence).
* **(gen)** — the name comes from a generated binding whose method names are mechanically derived from
  selectors; the colon placement has been reconstructed and may be slightly wrong. Treat the *name* as
  reliable and the *argument structure* as probable, not certain.

A caveat that applies to the whole file: `nst/iOS-Runtime-Headers` is an **iOS** dump and is old — it
predates `_ANEInMemoryModel` entirely (that class does not appear), so it reflects roughly the iOS 11–13
era of the framework [INFERRED from the class set; the repo was archived read-only on 2026-09-08]. Modern
macOS projects use the newer in-memory-model API, which the iOS dump does not contain.

---

## 1. Where it lives, and how a program reaches it

The framework bundle is at `/System/Library/PrivateFrameworks/AppleNeuralEngine.framework/`.
On this machine (Mac mini M4, macOS 27.0) the bundle contains a symlink
`AppleNeuralEngine -> Versions/Current/AppleNeuralEngine` whose target is **not** present on disk
(the dylib lives in the dyld shared cache), plus three XPC services [MEASURED — directory listing of
`/System/Library/PrivateFrameworks/AppleNeuralEngine.framework/XPCServices`]:

```
ANECompilerService.xpc
ANELargeModelCompilerService.xpc
ANEStorageMaintainer.xpc
```

Because the dylib is only in the shared cache, you cannot `nm` it directly; you `dlopen` by path (works,
the loader resolves from the cache) and then look classes up by name. Every project does exactly this:

```objc
// Source: maderix/ANE — bridge/ane_bridge.m
void *handle = dlopen(
    "/System/Library/PrivateFrameworks/AppleNeuralEngine.framework/AppleNeuralEngine",
    RTLD_NOW);
if (!handle) { /* framework load failed */ }

g_ANEDesc  = NSClassFromString(@"_ANEInMemoryModelDescriptor");
g_ANEInMem = NSClassFromString(@"_ANEInMemoryModel");
g_ANEReq   = NSClassFromString(@"_ANERequest");
g_ANEIO    = NSClassFromString(@"_ANEIOSurfaceObject");
```

The same pattern, in C++ with `sel_registerName` instead of `@selector`, is in
`johnmai-dev/ANE-LM` `core/ane_runtime.cpp:135` and `AmiraniLabs/libane` `src/runtime/ane_runtime.mm:294`.
`thebasedcapital/ane-infer` additionally loads `_ANEClient` for a daemon-bypassing eval path
(`crates/ane-bridge/objc/ane_runtime.m:55-63`).

**No entitlement is needed for this path on macOS.** maderix's bridge builds as a plain unsigned dylib
(`bridge/Makefile`: `clang -fobjc-arc -dynamiclib ... -framework Foundation -framework IOSurface -ldl`)
and works [MEASURED — the project ships benchmark results produced this way]. The entitlement
`com.apple.ane.iokit-user-access` appears in geohot's tinygrad `extra/accel/ane/3_run/entitlements.xml`,
but that is for the **direct H11ANE IOKit** path, not the framework path.

---

## 2. The class map

Class inventory below is from the generated current-macOS bindings in `tmc/apple`
(`private/appleneuralengine/*.gen.go`, one file per class) [DOCUMENTED], cross-checked against
class names actually resolved at runtime by working projects [MEASURED].

| Class | What it is, in plain English | Used by |
|---|---|---|
| `_ANEInMemoryModelDescriptor` | The *description* of a model you are about to compile: MIL program text + weight blobs + an options plist. A factory object; the model is not compiled yet. | maderix, ANE-LM, libane, ane-infer |
| `_ANEInMemoryModel` | The workhorse. Wraps a descriptor and owns the compile → load → evaluate → unload lifecycle, plus the temp directory the compiler writes into. | all of the above |
| `_ANEInMemoryModelDescriptor`-derived `_ANEModel` | The *kernel-side handle* for a loaded program: program handle, UUID, `string_id`, model attributes, IOSurface mapper. `_ANEInMemoryModel` exposes one via `-model`. | ane-infer (chaining), libane (Path B) |
| `_ANECompiler...` | See §3.11 — the widely-cited name `_ANECompiler` is **not** a class in the dump. | — |
| `_ANERequest` | One evaluation request: which input surfaces, which output surfaces, in what order, which procedure, optional perf-stats buffer / shared events / transaction handle / completion block. | all |
| `_ANEIOSurfaceObject` | Thin wrapper turning a raw `IOSurfaceRef` into an ObjC object the request can hold, optionally with a `startOffset`. | all |
| `_ANEProgramForEvaluation` | The loaded program itself, on the device. Exposes the low-overhead `processRequest:...` dispatch that bypasses `_ANEInMemoryModel`. | libane (fast path) |
| `_ANEDeviceController` | Owns the device connection for a program handle; holds a raw 3-pointer device struct and a use count. `start`/`stop`. | libane |
| `_ANEDeviceInfo` | **Class-method-only** introspection: architecture string, core count, board type, build version, boot args. | libane, ane-infer |
| `_ANEStrings` | Central constants: error domains, entitlements, cache/temp directories, default file names (`model.mil`, `model.hwx`, …), mach service names. | (headers) |
| `_ANEErrors` | Error factories, one per failure class (`programCreationErrorForMethod:`, `programLoadErrorForMethod:`, `entitlementErrorForMethod:`, …). | (headers) |
| `_ANEQoSMapper` | Maps QoS values to program priority and queue index. Explains the magic `21` everyone hardcodes. | (headers) |
| `_ANELog`, `_ANEDataReporter`, `_ANEHashEncoding`, `_ANECloneHelper`, `_ANESandboxingHelper`, `_ANEModelToken`, `_ANEWeight`, `_ANEProcedureData`, `_ANEVirtualClient` | Logging, telemetry, hashing, clone/copy of model files, sandbox extensions, model tokens, per-weight references, per-procedure weight arrays, a virtualization client. | mostly unused in public projects |
| `_ANEChainingRequest`, `_ANEBuffer`, `_ANEIOSurfaceOutputSets`, `_ANEInputBuffersReady`, `_ANEOutputSetEnqueue`, `_ANESharedEvents`, `_ANESharedSignalEvent`, `_ANESharedWaitEvent` | Firmware-level pipeline chaining and cross-engine signalling. Partly reachable; see §3.10 and §6. The shared-event trio is now **runtime-verified on M5 Max / macOS 27.0.1** — `IOSurfaceSharedEvent`-backed, mach-port bridgeable to `MTLSharedEvent`; see §3.12 and `results/EXP-025-ane-gpu-sync/`. | ane-infer (explored), libane (explored, blocked), EXP-025 (measured) |
| `_ANEPerformanceStats`, `_ANEPerformanceStatsIOSurface`, `_ANEProgramIOSurfacesMapper`, `_ANEModelInstanceParameters` | Per-eval performance counters, perf-stats-in-a-surface, the IOSurface→IOVA mapper, and per-instance load parameters. | headers only |
| `_ANECompilerServiceProtocol`, `_ANEDaemonProtocol`, `_ANEStorageMaintainerProtocol`, `_ANEMaintenanceProtocol` | XPC protocols implemented by the three `.xpc` services above. | headers only |

---

## 3. Class-by-class signatures

### 3.1 `_ANEInMemoryModelDescriptor`

The only factory anyone uses in practice is `modelWithMILText:weights:optionsPlist:` [MEASURED —
call-site in maderix, ANE-LM, libane, ane-infer].

```objc
// Source: AmiraniLabs/libane — src/runtime/ane_runtime.mm
// MIL text must be NSData (UTF-8 bytes), never NSString.
NSData *mil_data = [NSData dataWithBytes:mil_text.data() length:mil_text.size()];

// Key = the exact BLOBFILE path from the MIL program.
// Value = @{ @"offset": @0, @"data": <NSData blob> }
NSMutableDictionary *weights_dict = [NSMutableDictionary dictionary];
for (const auto &w : weights) {
    NSString *full_path = [NSString stringWithFormat:@"@model_path/weights/%s", w.filename.c_str()];
    NSData   *blob      = [NSData dataWithBytes:w.data.data() length:w.data.size()];
    weights_dict[full_path] = @{@"offset": @0, @"data": blob};
}
// CRITICAL: must be @{} (empty dict), never nil, for weight-free programs.
NSDictionary *final_weights = (weights_dict.count > 0) ? weights_dict : @{};

id descriptor = ((id(*)(Class,SEL,id,id,id))objc_msgSend)(
    g_syms.cls_Descriptor,
    g_syms.sel_modelWithMILText,          // "modelWithMILText:weights:optionsPlist:"
    mil_data, final_weights, nil);        // third arg: optionsPlist, nil in practice
```

Full method list from the generated bindings [DOCUMENTED, (gen) for colon structure]:

```objc
+ (id)modelWithMILText:(NSData *)milText weights:(NSDictionary *)weights optionsPlist:(id)plist;
+ (id)modelWithNetworkDescription:(id)desc weights:(NSDictionary *)weights optionsPlist:(id)plist;
- (id)initWithNetworkText:(id)text weights:(id)weights optionsPlist:(id)plist isMILModel:(BOOL)isMIL;
- (id)hexStringIdentifier;
- (BOOL)isEqualToInMemoryModelDescriptor:(id)other;
- (BOOL)isMILModel;
- (NSData *)networkText;      - (NSString *)networkTextHash;
- (NSData *)optionsPlist;     - (NSString *)optionsPlistHash;
- (NSDictionary *)weights;    - (NSString *)weightsHash;
```

`modelWithNetworkDescription:...` is the non-MIL (Espresso/network-plist) sibling and is not exercised by
any project I read. `hexStringIdentifier` on the descriptor is a hash of the program; the **model**'s own
`hexStringIdentifier` is what projects use as a temp-directory name.

### 3.2 `_ANEInMemoryModel`

Create it from a descriptor, then compile/load/evaluate/unload [MEASURED — call-site in four projects]:

```objc
id mdl = ((id(*)(Class,SEL,id))objc_msgSend)(
    g_ANEInMem, @selector(inMemoryModelWithDescriptor:), desc);   // + (id)inMemoryModelWithDescriptor:(id)
```

The lifecycle calls, all with the same three shapes [MEASURED — call-site, identical in maderix,
ANE-LM, libane, ane-infer]:

```objc
// QoS 21 everywhere; options is @{} (never nil) in every working call site.
- (BOOL)compileWithQoS:(unsigned int)qos options:(id)options error:(NSError **)error;
- (BOOL)loadWithQoS:(unsigned int)qos    options:(id)options error:(NSError **)error;
- (BOOL)evaluateWithQoS:(unsigned int)qos options:(id)options request:(id)req error:(NSError **)error;
- (BOOL)unloadWithQoS:(unsigned int)qos error:(NSError **)error;
```

Full instance-method inventory [DOCUMENTED, (gen)] — this list is the single best cross-check on the
ane-infer ivar map in §6:

```objc
- (BOOL)compileWithQoS:(uint32_t)qos options:(id)options error:(NSError **)error;
- (BOOL)compiledModelExists;
- (id)compilerOptionsFileName;                      - (void)setCompilerOptionsFileName:(id);
- (id)compilerOptionsWithOptions:(id)options isCompiledModelCached:(BOOL)cached;
- (id)descriptor;                                   - (void)setDescriptor:(id);
- (BOOL)evaluateWithQoS:(uint32_t)qos options:(id)options request:(id)request error:(NSError **)error;
- (NSString *)hexStringIdentifier;
- (uint64_t)intermediateBufferHandle;               - (void)setIntermediateBufferHandle:(uint64_t);
- (BOOL)isMILModel;
- (BOOL)loadWithQoS:(uint32_t)qos options:(id)options error:(NSError **)error;
- (id)localModelPath;
- (BOOL)mapIOSurfacesWithRequest:(id)request cacheInference:(BOOL)cache error:(NSError **)error;
- (id)model;                                        - (void)setModel:(id);            // -> _ANEModel
- (NSDictionary *)modelAttributes;                  - (void)setModelAttributes:(NSDictionary *);
- (NSURL *)modelURL;                                - (void)setModelURL:(NSURL *);
- (uint32_t)perfStatsMask;                          - (void)setPerfStatsMask:(uint32_t);
- (id)program;                                      - (void)setProgram:(id);          // -> _ANEProgramForEvaluation
- (uint64_t)programHandle;                          - (void)setProgramHandle:(uint64_t);
- (void)purgeCompiledModel;
- (int8_t)queueDepth;                               - (void)setQueueDepth:(int8_t);
- (id)saveModelFiles;
- (id)sharedConnection;                                                               // -> _ANEClient
- (uint64_t)state;                                  - (void)setState:(uint64_t);
- (uint64_t)string_id;
- (BOOL)unloadWithQoS:(uint32_t)qos error:(NSError **)error;
- (void)unmapIOSurfacesWithRequest:(id)request;
- (id)initWithDesctiptor:(id)descriptor;            // [sic] "Desctiptor" is Apple's typo, in the selector
```

Two of these are used as health signals in practice:

* `hexStringIdentifier` — used as the temp-dir name. Every project does
  `NSTemporaryDirectory()/<hexID>`, writes `model.mil` and `weights/*` there, then compiles.
  libane falls back to a fresh `NSUUID` if it comes back empty [MEASURED — call-site].
* `intermediateBufferHandle` — ane-infer reads it as "non-zero means the model spilled its intermediates
  out of on-chip SRAM to DRAM" [CLAIMED; ane-infer is the only source, and libane reports it is *always*
  `0` on the MIL path, which is a different statement, not a contradiction of the spill meaning].

### 3.3 `_ANERequest`

The classic factory, used by every project [MEASURED — call-site]:

```objc
// Source: maderix/ANE — bridge/ane_bridge.m
k->request = ((id(*)(Class,SEL,id,id,id,id,id,id,id))objc_msgSend)(
    g_ANEReq,
    @selector(requestWithInputs:inputIndices:outputs:outputIndices:weightsBuffer:perfStats:procedureIndex:),
    wIns,          // NSArray<_ANEIOSurfaceObject *>
    iIdx,          // NSArray<NSNumber *>   indices into the model's input symbols
    wOuts,         // NSArray<_ANEIOSurfaceObject *>
    oIdx,          // NSArray<NSNumber *>
    nil,           // weightsBuffer  (nil in all public call sites)
    nil,           // perfStats
    @0);           // procedureIndex (NSNumber)
```

`thebasedcapital/ane-infer` uses the same selector with `@(p)` as `procedureIndex` to address the
*p*-th procedure of a multi-function MIL program (`ane_runtime.m`, compile path). The generated bindings
show a whole family of factories [DOCUMENTED, (gen)]:

```objc
+ (id)requestWithInputs:inputIndices:outputs:outputIndices:procedureIndex:;
+ (id)requestWithInputs:inputIndices:outputs:outputIndices:perfStats:procedureIndex:;
+ (id)requestWithInputs:inputIndices:outputs:outputIndices:weightsBuffer:procedureIndex:;
+ (id)requestWithInputs:inputIndices:outputs:outputIndices:weightsBuffer:perfStats:procedureIndex:;
+ (id)requestWithInputs:inputIndices:outputs:outputIndices:weightsBuffer:perfStats:procedureIndex:sharedEvents:;
+ (id)requestWithInputs:inputIndices:outputs:outputIndices:weightsBuffer:perfStats:procedureIndex:sharedEvents:transactionHandle:;
- (id)initWithInputs:inputIndices:outputs:outputIndices:weightsBuffer:perfStats:procedureIndex:sharedEvents:transactionHandle:;
- (id)initWithVirtualModel:(void *)model;
- (uint64_t)ioSurfacesCount;
- (BOOL)validate;
- (void)setCompletionHandler:(void (^)(id))handler;
// properties: inputArray, inputIndexArray, outputArray, outputIndexArray,
//             perfStats, perfStatsArray, procedureIndex, sharedEvents, transactionHandle, weightsBuffer
```

The `sharedEvents:` family above is now runtime-confirmed on this M5 Max / 27.0.1 with the slot
exercised live: populated objects attach without complaint client-side, the dispatch reads them 4×
per eval, and consumption is package-gated — §3.12, `results/EXP-025-ane-gpu-sync/` [MEASURED].

`setCompletionHandler:` is the interesting one: it fires asynchronously **after** `evaluateWithQoS:`
returns, on a thread libane identifies as `ANEServicesThread`, with the IOSurface already coherent
[MEASURED — libane `docs/ane-runtime-boundary.md`, timing given as eval ≈ 0.1–0.4 ms then handler
≈ 0.2 ms later].

### 3.4 `_ANEIOSurfaceObject`

```objc
// Source: maderix/ANE — bridge/ane_bridge.m  (and identically in ANE-LM and ane-infer)
[g_ANEIO objectWithIOSurface:k->ioInputs[i]]     // + (id)objectWithIOSurface:(IOSurfaceRef)
```

Full surface [DOCUMENTED, (gen)]:

```objc
+ (IOSurfaceRef)createIOSurfaceWithWidth:(int)w pixel_size:(int)px height:(int)h;
+ (IOSurfaceRef)createIOSurfaceWithWidth:(int)w pixel_size:(int)px height:(int)h bytesPerElement:(int)bpe;
+ (id)objectWithIOSurface:(IOSurfaceRef)surf;
+ (id)objectWithIOSurface:(IOSurfaceRef)surf startOffset:(NSNumber *)offset;
+ (id)objectWithIOSurfaceNoRetain:(IOSurfaceRef)surf startOffset:(NSNumber *)offset;
- (id)initWithIOSurface:(IOSurfaceRef)surf startOffset:(NSNumber *)offset shouldRetain:(BOOL)retain;
- (IOSurfaceRef)ioSurface;   - (NSNumber *)startOffset;
```

The two factory forms matter: maderix/ANE-LM use the plain `objectWithIOSurface:`; libane's Path B uses
`alloc` + `initWithIOSurface:startOffset:shouldRetain:` because it needs the offset and the retain
semantics [MEASURED — call-site]. Per libane, `startOffset` is **ignored by DMA on the MIL path** and
only has an effect when the model was loaded through `_ANEClient` (Path B), because the offset lives in a
firmware IOVA mapping that only Path B registers [MEASURED — libane, swept offsets 1…16 K with zero
observable effect].

### 3.5 `_ANEModel`

This is the object the *firmware* knows about; `_ANEInMemoryModel` wraps one. ane-infer states the
relationship explicitly: "`_ANEInMemoryModel` is the ObjC wrapper…, `_ANEModel` is the kernel handle…
access via `[inMemModel model]`" [CLAIMED but consistent with the class dump].

Factory used by libane's Path B [MEASURED — call-site]:

```objc
// Source: AmiraniLabs/libane — src/runtime/ane_runtime.mm
id client = ((id(*)(Class,SEL))objc_msgSend)(g_syms.cls_ANEClient, g_syms.sel_sharedConnection);
id model  = ((id(*)(Class,SEL,NSURL*,NSString*))objc_msgSend)(
    g_syms.cls_ANEModel_b, g_syms.sel_modelAtURLKey, dir_url, dir_ns);   // "modelAtURL:key:"
```

The iOS-era header had exactly two factories; the current dump has many more
[DOCUMENTED, (gen) — the argument names are reconstructed and the `source:` integer's meaning is unknown]:

```objc
+ (id)modelAtURL:(NSURL *)url key:(NSString *)key;
+ (id)modelAtURL:(NSURL *)url key:(NSString *)key modelAttributes:(NSDictionary *)attrs;
+ (id)modelAtURL:(NSURL *)url key:(NSString *)key mpsConstants:(id)constants;
+ (id)modelAtURLWithCacheURLIdentifier:(id)uRLIdentifier key:(id)key cacheURLIdentifier:(id)uRLIdentifier2;
+ (id)modelAtURLWithSourceURL:(NSURL *)url sourceURL:(NSURL *)url2 key:(id)key cacheURLIdentifier:(id);
+ (id)modelAtURLWithSourceURL:(NSURL *)url sourceURL:(NSURL *)url2 key:(id)key identifierSource:(int64_t)
        cacheURLIdentifier:(id) uRLIdentifier;
+ (id)modelAtURLWithSourceURL:(NSURL *)url sourceURL:(NSURL *)url2 key:(id)key identifierSource:(int64_t)
        cacheURLIdentifier:(id) uRLIdentifier uuid:(NSUUID *)uid;
+ (id)modelWithCacheURLIdentifier:(id)uRLIdentifier;
+ (id)modelWithCacheURLIdentifier:(id)uRLIdentifier uuid:(NSUUID *)uid;
+ (id)correctFileURLFormat:(id)format;
```

Readable state on the instance [DOCUMENTED, (gen) + MEASURED for the first four via ane-infer and libane]:

```objc
- (uint64_t)intermediateBufferHandle;   - (void)setIntermediateBufferHandle:(uint64_t);
- (id)mapper;                           // -> _ANEProgramIOSurfacesMapper
- (uint64_t)string_id;                  - (void)setString_id:(uint64_t);
- (uint64_t)programHandle;              - (void)setProgramHandle:(uint64_t);
- (id)program;                          // -> _ANEProgramForEvaluation
- (NSUUID *)uuid;                       - (id)getUUID;            - (id)getCacheURLIdentifier;
- (uint64_t)state;                      - (void)setState:(uint64_t);
- (int8_t)queueDepth;                   - (void)setQueueDepth:(int8_t);
- (NSDictionary *)modelAttributes;      - (void)setModelAttributes:(NSDictionary *);
- (uint32_t)perfStatsMask;              - (void)setPerfStatsMask:(uint32_t);
- (NSString *)key;  - (NSURL *)modelURL;  - (NSURL *)sourceURL;  - (NSString *)cacheURLIdentifier;
- (id)inputSymbolIndicesForProcedureIndex:(uint32_t)index;
- (id)outputSymbolIndicesForProcedureIndex:(uint32_t)index;
- (id)procedureInfoForProcedureIndex:(uint32_t)index;
- (void)updateModelAttributes:(id)attrs state:(uint64_t)state programHandle:(uint64_t)ph
        intermediateBufferHandle:(uint64_t)ibh queueDepth:(int8_t)depth;
- (void)resetOnUnload;  - (id)shallowCopy;  - (BOOL)isEqualToModel:(id)other;
```

`string_id` is the value libane passes as `modelStringID:` to `processRequest:`. libane reads it via KVC
(`[inner valueForKey:@"model"]` then `valueForKey:@"program"`, then `sel_registerName("string_id")`)
because it never links headers [MEASURED — call-site].

`modelAttributes` is a plain `NSDictionary` and is the best introspection hook on the whole framework.
ane-infer walks it to discover multi-procedure models [MEASURED — call-site]:

```objc
// Source: thebasedcapital/ane-infer — crates/ane-bridge/objc/ane_runtime.m
id attrs = ((id(*)(id,SEL))objc_msgSend)(aneModel, @selector(modelAttributes));
NSDictionary *fDesc = [attrs objectForKey:@"ANEFModelDescription"];
NSArray *procs      = [fDesc objectForKey:@"ANEFModelProcedures"];
// procs[i] = { ProcedureID, InputSymbolIndexArray, OutputSymbolIndexArray }
// ProcedureNameToIDMap: { layer0: 0, layer1: 1 }
```

ane-infer's documented caution, worth repeating verbatim in spirit: for a multi-function program,
procedure *N* uses `inputIndex = N` and `outputIndex = N` — not index 0 — and using the wrong indices
returns error `0x2` [MEASURED — ane-infer `docs/ane-internals.md`].

Reported object description shape, from a live debugger session on the daemon side
[MEASURED — tinygrad `extra/accel/ane/README.md`, an lldb capture of `-[_ANEDaemonConnection loadModel:...]`]:

```
_ANEModel: { modelURL=file:///.../test_<UUID>.mlmodelc/ :
             key={"isegment":0,
                  "inputs":{"image":{"shape":[1,1,1,64,1]}, "image2":{"shape":[1,1,1,64,1]}},
                  "outputs":{"probs":{"shape":[1,1,1,64,1]}}} :
             string_id=0x00000000 : program=(null) : state=1 :
             programHandle=0 : intermediateBufferHandle=0 : queueDepth=0 : attr={} : perfStatsMask=0 }
```

### 3.6 `_ANEClient`

This is the daemon-facing client. Older dumps describe it as a thin XPC proxy with a shared connection:

```objc
// Source: nst/iOS-Runtime-Headers — PrivateFrameworks/AppleNeuralEngine.framework/_ANEClient.h
// (old iOS-era API, DOCUMENTED)
+ (id)sharedConnection;   + (id)sharedPrivateConnection;
+ (id)sandboxExtensionForModel:(id)model;
- (id)initWithRestrictedAccessAllowed:(BOOL)allowed;
- (bool)compileModel:(id)model options:(id)options qos:(unsigned int)qos error:(NSError **)error;
- (bool)loadModel:(id)model options:(id)options qos:(unsigned int)qos error:(NSError **)error;
- (bool)doLoadModel:(id)model options:(id)options qos:(unsigned int)qos error:(NSError **)error;
- (bool)unloadModel:(id)model options:(id)options qos:(unsigned int)qos error:(NSError **)error;
- (bool)doUnloadModel:(id)model options:(id)options qos:(unsigned int)qos error:(NSError **)error;
- (bool)evaluateWithModel:(id)model options:(id)options request:(id)req qos:(unsigned int)qos error:(NSError **)error;
- (bool)doEvaluateDirectWithModel:(id)model request:(id)req qos:(unsigned int)qos error:(NSError **)error;
- (bool)evaluateRealTimeWithModel:(id)model options:(id)options request:(id)req error:(NSError **)error;
- (bool)loadRealTimeModel:(id)model options:(id)options qos:(unsigned int)qos error:(NSError **)error;
- (bool)unloadRealTimeModel:(id)model options:(id)options qos:(unsigned int)qos error:(NSError **)error;
- (bool)beginRealTimeTask;  - (bool)endRealTimeTask;  - (bool)echo:(id)obj;
@property (nonatomic, readonly) _ANEDaemonConnection *conn;
@property (nonatomic, readonly) NSArray *queues;
```

**Note the 4-argument `doEvaluateDirectWithModel:request:qos:error:` in the old header versus the
5-argument `doEvaluateDirectWithModel:options:request:qos:error:` used by every modern project.** Both are
attested; they are different framework generations. Modern form, from two independent projects:

```objc
// Source: AmiraniLabs/libane — src/runtime/ane_runtime.mm  (sel string registered verbatim)
g_syms.sel_doEvalDirect = sel_registerName("doEvaluateDirectWithModel:options:request:qos:error:");
...
((EvalDirectFn)objc_msgSend)(client, g_syms.sel_doEvalDirect, model_b, @{}, request, kQoS, &error);

// Source: thebasedcapital/ane-infer — crates/ane-bridge/objc/ane_runtime.m
ok = ((BOOL(*)(id,SEL,id,id,id,unsigned int,NSError**))objc_msgSend)(
    g_client, @selector(doEvaluateDirectWithModel:options:request:qos:error:),
    k->model, @{}, k->request, 21, &error);
```

Acquiring the client, in ane-infer's form [MEASURED — call-site]:

```objc
// Source: thebasedcapital/ane-infer
g_client = ((id(*)(id,SEL,BOOL))objc_msgSend)(
    [g_ANEClient alloc], @selector(initWithRestrictedAccessAllowed:), YES);
```

libane instead uses `[_ANEClient sharedConnection]` for Path B [MEASURED].
Current generated inventory [DOCUMENTED, (gen)], grouped:

```objc
// lifecycle
- (BOOL)compileModel:(id)model options:(id)options qos:(uint32_t)qos error:(NSError **)error;
- (BOOL)loadModel:(id)model options:(id)options qos:(uint32_t)qos error:(NSError **)error;
- (BOOL)doLoadModel:(id)model options:(id)options qos:(uint32_t)qos error:(NSError **)error;
- (BOOL)unloadModel:(id)model options:(id)options qos:(uint32_t)qos error:(NSError **)error;
- (BOOL)doUnloadModel:(id)model options:(id)options qos:(uint32_t)qos error:(NSError **)error;
- (BOOL)loadModelNewInstance:(id)inst options:(id)options modelInstParams:(id)params qos:(uint32_t)qos error:(NSError **)error;
- (BOOL)doLoadModelNewInstance:(id)inst options:(id)options modelInstParams:(id)params qos:(uint32_t)qos error:(NSError **)error;
- (BOOL)loadRealTimeModel:...  - (BOOL)unloadRealTimeModel:...
// evaluation
- (BOOL)evaluateWithModel:(id)model options:(id)options request:(id)req qos:(uint32_t)qos error:(NSError **)error;
- (BOOL)doEvaluateDirectWithModel:(id)model options:(id)options request:(id)req qos:(uint32_t)qos error:(NSError **)error;
- (BOOL)evaluateRealTimeWithModel:(id)model options:(id)options request:(id)req error:(NSError **)error;
// surfaces
- (BOOL)mapIOSurfacesWithModel:(id)model request:(id)req cacheInference:(BOOL)cache error:(NSError **)error;
- (void)unmapIOSurfacesWithModel:(id)model request:(id)req;
// chaining
- (BOOL)prepareChainingWithModel:(id)model options:(id)options chainingReq:(id)req qos:(uint32_t)qos error:(NSError **)error;
- (BOOL)doPrepareChainingWithModel:(id)model options:(id)options chainingReq:(id)req qos:(uint32_t)qos error:(NSError **)error;
- (BOOL)buffersReadyWithModel:(id)model inputBuffers:(id)buffers options:(id)options qos:(uint32_t)qos error:(NSError **)error;
- (BOOL)doBuffersReadyWithModel:(id)model inputBuffers:(id)buffers options:(id)options qos:(uint32_t)qos error:(NSError **)error;
- (BOOL)enqueueSetsWithModel:(id)model outputSet:(id)set options:(id)options qos:(uint32_t)qos error:(NSError **)error;
- (BOOL)doEnqueueSetsWithModel:(id)model outputSet:(id)set options:(id)options qos:(uint32_t)qos error:(NSError **)error;
// session / diagnostics
- (BOOL)sessionHintWithModel:(id)model hint:(NSString *)hint options:(id)options report:(id)report error:(NSError **)error;
- (void)reportEvaluateFailure:(id)failure failureReason:(uint32_t)reason qIdx:(uint64_t)idx;
- (BOOL)beginRealTimeTask;  - (BOOL)endRealTimeTask;  - (BOOL)echo:(id)obj;
// cache / introspection / internals
- (BOOL)compiledModelExistsFor:(id)model;   - (BOOL)compiledModelExistsMatchingHash:(id)hash;
- (void)purgeCompiledModel:(id)model;       - (void)purgeCompiledModelMatchingHash:(id)hash;
- (id)connections;  - (id)connectionsUsedForLoadingModels;
- (id)connectionForLoadingModel:(id)model options:(id)options;
- (id)connectionUsedForLoadingModel:(id)model;
- (BOOL)isAnetoolRootDaemonConnection;  - (BOOL)isVirtualClient;  - (BOOL)isRootDaemon;
- (BOOL)allowRestrictedAccess;  - (id)conn;  - (id)fastConn;  - (id)fastConnWithoutLock;  - (id)priorityQ;
@property (readonly) id conn;  @property (readonly) id fastConn;  @property (readonly) id virtualClient;
+ (id)sharedConnection;  + (id)sharedPrivateConnection;
```

The `do`-prefixed variants are the ones that skip the daemon XPC hop. Every project that uses them says
they are faster than the non-`do` form; the two published measurements disagree with each other on
magnitude and, in one case, on sign — see §8.

### 3.7 `_ANEProgramForEvaluation`

```objc
// Source: AmiraniLabs/libane — src/runtime/ane_runtime.mm  (the fast dispatch path)
typedef BOOL (*ProcReqFn)(id, SEL, id, id, unsigned int, uint64_t, uint64_t, id, uint32_t*, NSError**);
BOOL ok = ((ProcReqFn)objc_msgSend)(
    prog_eval,                                  // _ANEProgramForEvaluation
    g_syms.sel_processRequest,                  // "processRequest:model:qos:qIndex:modelStringID:options:returnValue:error:"
    request,
    inner_model,                                // _ANEModel
    kQoS,                                       // 21
    (uint64_t)0,                                // qIndex
    program->model_string_id,                   // from _ANEModel.string_id
    @{},                                        // options
    &ret_val,                                   // uint32_t* returnValue
    &error);
```

Full surface [DOCUMENTED, (gen)]:

```objc
- (BOOL)processRequest:(id)req model:(id)model qos:(uint32_t)qos qIndex:(uint64_t)qIndex
        modelStringID:(uint64_t)stringID options:(id)options returnValue:(uint32_t *)value error:(NSError **)error;
- (BOOL)processInputBuffers:(id)buffers model:(id)model options:(id)options error:(NSError **)error;
- (BOOL)processOutputSet:(id)set model:(id)model options:(id)options error:(NSError **)error;
- (BOOL)processSessionHint:(NSString *)hint options:(id)options report:(id)report error:(NSError **)error;
- (id)programInferenceOtherErrorForMessage:(ANENotificationMessageStruct *)msg model:(id)model methodName:(id)name;
+ (id)programWithHandle:(uint64_t)handle;
+ (id)programWithHandle:(uint64_t)handle intermediateBufferHandle:(uint64_t)ibh queueDepth:(int8_t)depth;
+ (id)programWithController:(id)controller intermediateBufferHandle:(uint64_t)ibh queueDepth:(int8_t)depth;
- (uint64_t)programHandle;  - (uint64_t)intermediateBufferHandle;  - (int64_t)currentAsyncRequestsInFlight;
- (int8_t)queueDepth;  - (id)controller;  - (id)requestsInFlight;
```

Reached from `_ANEInMemoryModel` by KVC, as libane does [MEASURED — call-site]:
`[model valueForKey:@"model"]` → `_ANEModel`, then `[inner valueForKey:@"program"]`.

### 3.8 `_ANEDeviceInfo` (class methods only)

libane's runtime comment is the clearest statement of this: *"`_ANEDeviceInfo` exposes ONLY class methods
(no instance methods). Call them directly on the Class object — do NOT alloc/init an instance."*
[MEASURED — libane]. The full current list [DOCUMENTED, (gen)]:

```objc
+ (NSString *)aneArchitectureType;   // "h15g" (M3), "h16g" (M4) …      [measured on M3 by libane]
+ (uint32_t)numANECores;             // number of inference cores
+ (uint32_t)numANEs;                 // number of ANE units (usually 1)
+ (int64_t)aneBoardType;   + (NSString *)aneSubType;   + (NSString *)aneSubTypeAndVariant;
+ (NSString *)aneSubTypeProductVariant;   + (NSString *)aneSubTypeVariant;
+ (NSString *)productName;   + (NSString *)buildVersion;   + (id)bootArgs;
+ (BOOL)hasANE;   + (BOOL)isInternalBuild;   + (BOOL)isVirtualMachine;
+ (BOOL)isBootArgPresent:(id)arg;   + (BOOL)isBoolBootArgSetTrue:(id)arg;
+ (BOOL)isExcessivePowerDrainWhenIdle;   + (BOOL)precompiledModelChecksDisabled;
```

Note `+hasANE` exists in both the old iOS header and the current dump, i.e. it is stable across a decade.

### 3.9 `_ANEDeviceController`, `_ANEQoSMapper`, `_ANEStrings`, `_ANEErrors`

```objc
// _ANEDeviceController  [DOCUMENTED, (gen)] — libane has also seen -device and -usecount in use
+ (id)controllerWithProgramHandle:(uint64_t)handle;
+ (id)controllerWithPrivilegedVM:(BOOL)vm;
+ (id)sharedPrivilegedConnection;
- (id)initWithProgramHandle:(uint64_t)handle priviledged:(BOOL)priv;   // [sic] "priviledged"
- (id)initWithANEPrivilegedVM:(BOOL)vm;
- (void)start;   - (void)stop;
- (struct ANEDeviceStruct *)device;   - (void)setDevice:(struct ANEDeviceStruct *);
- (BOOL)isPrivileged;   - (uint64_t)programHandle;   - (int64_t)usecount;
// ANEDeviceStruct = { void *field1; void *field2; void *field3; char; int; uint64 };
// "raw kernel handles (3 void pointers)" per ane-infer's notes.
```

```objc
// _ANEQoSMapper  [DOCUMENTED, (gen)] — the explanation for the constant 21
+ (uint32_t)aneDefaultTaskQoS;      + (uint32_t)aneUtilityTaskQoS;
+ (uint32_t)aneBackgroundTaskQoS;   + (uint32_t)aneRealTimeTaskQoS;
+ (uint32_t)aneUserInitiatedTaskQoS; + (uint32_t)aneUserInteractiveTaskQoS;
+ (int)programPriorityForQoS:(uint32_t)qos;      + (uint32_t)qosForProgramPriority:(int)priority;
+ (uint64_t)queueIndexForQoS:(uint32_t)qos;
+ (int)realTimeProgramPriority;     + (uint64_t)realTimeQueueIndex;
+ (id)dispatchQueueArrayByMappingPrioritiesWithTag:(id)tag;
```

Nobody in the public sources *calls* `aneDefaultTaskQoS`; they hardcode `21`. That `21 ==
aneDefaultTaskQoS` is my [INFERRED] reading, not a measured fact.

```objc
// _ANEStrings  [DOCUMENTED, (gen)] — a sample; the current dump lists ~60 such constants
+ (id)errorDomainCompiler;   + (id)errorDomainEspresso;   + (id)errorDomainGeneric;  + (id)errorDomainVirtIO;
+ (id)compilerServiceAccessEntitlement;   + (id)restrictedAccessEntitlement;
+ (id)storageMaintainerAccessEntitlement; + (id)secondaryANECompilerServiceAccessEntitlement;
+ (id)adapterWeightsAccessEntitlement;    + (id)processModelShareAccessEntitlement;
+ (id)memoryUnwireAccessEntitlement;      + (id)modelPurgeInAllPartitionsEntitlement;
+ (id)aggressivePowerSavingEntitlement;
+ (id)machServiceName;  + (id)machServiceNamePrivate;
+ (id)cloneDirectory;   + (id)cacheDirectory;   + (id)tempDirectory;
+ (id)modelDataVaultDirectory;   + (id)systemModelsCacheDirectory;   + (id)inMemoryModelCacheName;
+ (id)defaultMILFileName;  + (id)defaultMLIRFileName;  + (id)defaultANECIRFileName;
+ (id)defaultCompilerOptionsFilename;  + (id)defaultWeightFileName;  + (id)binExtension; + (id)hwxExtension;
```

```objc
// _ANEErrors  [DOCUMENTED, (gen)] — one factory per failure class; the method name says where it fires
+ (id)createErrorWithCode:(int64_t)code description:(id)desc;
+ (id)programCreationErrorForMethod:(id)method;   + (id)programLoadErrorForMethod:(id)method;
+ (id)programInferenceOtherErrorForMethod:(id)method;
+ (id)programInferenceOverflowErrorForMethod:(id)method;
+ (id)programIOSurfacesMapErrorForMethod:(id)method code:(int64_t)code;
+ (id)programChainingPrepareErrorForMethod:(id)method;
+ (id)entitlementErrorForMethod:(id)method;      + (id)missingCodeSigningErrorForMethod:(id)method;
+ (id)priorityErrorForMethod:(id)method;         + (id)timeoutErrorForMethod:(id)method;
+ (id)invalidModelErrorForMethod:(id)method;     + (id)invalidModelKeyErrorForMethod:(id)method;
+ (id)fileNotFoundErrorForMethod:(id)method;     + (id)fileAccessErrorForMethod:(id)method;
+ (id)notSupportedErrorForMethod:(id)method;     + (id)invalidModelInstanceErrorForMethod:(id)method;
+ (id)virtualizationHostError:(id)err error:(id)underlying;  /* + several more virtualization errors */
```

`programIOSurfacesMapErrorForMethod:code:` is very likely the source of the "error 13 / 0x12
(`Program IOSurfaces map failure`)" that libane hits on the MIL path — [INFERRED, not confirmed].

### 3.10 The chaining family

ane-infer mapped these and reports the correct factory for `_ANEIOSurfaceOutputSets` explicitly
[MEASURED — ane-infer; it took them several probes and a wrong name returns error 15]:

```objc
// Source: thebasedcapital/ane-infer — docs/ane-internals.md
@interface _ANEIOSurfaceOutputSets
+ (id)objectWithstatsSurRef:(IOSurfaceRef)outputBuffer:(NSArray<_ANEBuffer *> *)buffers;  // CORRECT
// + outputSetsWithBuffers:  ← does not exist; using it caused error 15
- (IOSurfaceRef)statsSurRef;  - (NSArray *)outputBuffer;
@end

@interface _ANEBuffer
+ (id)bufferWithIOSurfaceObject:(id)obj symbolIndex:(NSNumber *)idx source:(long long)src;  // 0=in, 1=out
@end

@interface _ANEInputBuffersReady
+ (id)inputBuffersWithProcedureIndex:(uint)idx inputBufferInfoIndex:(NSArray<NSNumber *> *)a
        inputFreeValue:(NSArray<NSNumber *> *)b executionDelay:(uint64_t)d;
@end

@interface _ANEOutputSetEnqueue
+ (id)outputSetWithProcedureIndex:(uint)idx setIndex:(uint)s signalValue:(uint64_t)v
        signalNotRequired:(BOOL)n isOpenLoop:(BOOL)o;
@end

@interface _ANEChainingRequest
+ (id)chainingRequestWithInputs:(NSArray *)inputs outputSets:(NSArray<_ANEIOSurfaceOutputSets *> *)sets
        lbInputSymbolId:(NSArray<NSNumber *> *)li lbOutputSymbolId:(NSArray<NSNumber *> *)lo
        procedureIndex:(NSNumber *)pi signalEvents:(NSArray *)ev
        transactionHandle:(NSNumber *)th fwEnqueueDelay:(NSNumber *)d memoryPoolId:(NSNumber *)mp;
- (BOOL)validate;
@end
```

The current dump shows the same factory as
`+chainingRequestWithInputs:outputSets:lbInputSymbolId:lbOutputSymbolId:procedureIndex:signalEvents:transactionHandle:fwEnqueueDelay:memoryPoolId:`
[DOCUMENTED, (gen)] — an independent confirmation of ane-infer's mapping.

Reported status: `prepareChainingWithModel:` **succeeds**, `buffersReadyWithModel:` fails silently, and
the sequence is mandatory (steps cannot be skipped) [CLAIMED — ane-infer]. libane independently reports
chaining is unreachable from the MIL path with **error 15** and traces the cause to
`intermediateBufferHandle == 0` [MEASURED — libane `docs/ane-runtime-boundary.md`]. Those two accounts
are compatible: ane-infer explored chaining on models loaded via `_ANEClient`.

### 3.11 `_ANECompiler` — a name, not (yet) a class

`_ANECompiler` is cited constantly in prose. Orion's Table 2 lists it as *"MIL → E5 microcode compilation"*,
and maderix's README says its APIs are reverse-engineered [both CLAIMED in that phrasing]. **It does not
appear in the current class dump** (`tmc/apple`), nor in the iOS dump, nor in any of the four working
codebases I read, all of which compile by calling `-[_ANEInMemoryModel compileWithQoS:options:error:]`
instead. What *does* exist nearby:

* `_ANECompilerServiceProtocol` — the XPC protocol implemented by `ANECompilerService.xpc` [DOCUMENTED].
* The error domain `com.apple.appleneuralengine.compiler` and the log/error prefix
  `"_ANECompiler : ANECCompile() FAILED"`, which is a *string produced by* the compiler service, not an
  ObjC class [DOCUMENTED — local knowledge base `coreai-model-zoo/knowledge/coreai-error-index.md:524-530`
  quotes the full error; `compression-reference.md:115` notes this string is usually noise].

So: "the `_ANECompiler` API" should be read as shorthand for "the compile step", which in the reachable
API is a method on `_ANEInMemoryModel` (Path A) or `_ANEClient` (Path B/Espresso).

`_ANEMemoryModel`, also named in the task brief, does not appear in the class dump, the iOS dump, any of
the four working codebases, or the papers I read. There is no evidence it exists; do not plan around it.

---

### 3.12 The shared-event trio — runtime-verified (2026-10-07, M5 Max, macOS 27.0.1)

Everything in this subsection was measured on this Studio in the ane-sync session; evidence lives in
`results/EXP-025-ane-gpu-sync/` (VERDICT.md carries the full chain). This is the partial answer to
"how can the GPU signal the ANE without a CPU round-trip".

**The three classes exist.** A runtime scan of 10,398 classes image-filtered to
AppleNeuralEngine.framework returns exactly `_ANESharedWaitEvent`, `_ANESharedSignalEvent` and
`_ANESharedEvents` (`results/class_dump.txt` in the pack).

**They carry `IOSurfaceSharedEvent` — a class absent from the 27 SDK.** Both event classes encode the
`_sharedEvent` ivar/property as `@"IOSurfaceSharedEvent"`; `_ANESharedEvents` holds `_signalEvents`/
`_waitEvents` NSArrays. No method or ivar in the trio mentions Metal, and AppleNeuralEngine and aned
link IOSurface + IOKit but **not Metal** (`otool -L` / `dyld_info -linked_dylibs`, pack `docs/SYMBOLS.md`).
`IOSurfaceSharedEvent` was found by in-process probe, not from headers (`results/surface_probe.txt`).

**The Metal bridge is a mach port.** `IOSurfaceSharedEvent` exposes `+initWithMachPort:`,
`+eventPort`, `-setSignaledValue:`, `-waitUntilSignaledValue:timeoutMS:` and ivar `_signaledValue`
`r^Q` (a shared-memory u64 counter); `MTLSharedEventHandle` exposes `-eventPort` (`I16@0:8`) whose
`_priv` struct begins with that port. Feed one into the other and both wrappers hold the **same kernel
event object**: our porttest crossed the boundary both ways — a Metal compute encoder
`encodeSignalEvent:` unblocked a wrapper-side wait in **~62 µs** (T2), and a wrapper-side signal
appeared on the `MTLSharedEvent` (T3) — `results/porttest.txt`; `results/lldb_shared_events.txt` shows
one `eventPort` (12339) observed identically through both API families.

**The eval dispatch consumes them.** Pid-provider dtrace on our own harness counts
`-[_ANERequest sharedEvents]` **exactly 4× per `processRequest:`** (6,744 reads / 1,686 evals) —
shared events are a first-class eval input, not debug metadata (`results/dtrace_ane_methods.txt.gz`).
A live lldb instance dump shows the signal-event ivars `value=42 symbolIndex=7 eventType=1 agentMask=1
sharedEvent=<IOSurfaceSharedEvent: …>` with raw layout at +8/16/24/32/40 matching the class-dump
encodings; `symbolIndex`/`agentMask` semantics remain unproven.

**Consumption on Path A crashes — documented behaviour, not only a bug report.** Attaching a populated
events object to an in-memory-MIL request SIGSEGVs deterministically at
`-[…processRequest:…_block_invoke +1524]`, fault addr 0x10 (pack FAILURES F11/F14, our own capture).
The `tmc/apple` Go bindings had guarded exactly this before our run:
`ErrSharedEventRequiresPackage` — "shared events require package-backed models (ModelTypePackage)"
(pkg.go.dev/github.com/tmc/apple/x/ane). Two independent parties, one mechanism: firmware honours
events only via the Path-B `intermediateBufferHandle` flow, i.e. **package-backed models only** (§5).
Their options table also names two tuning knobs we have not yet tested: `kANEFDisableIOFencesUseSharedEvents`
and `kANEFEnableFWToFWSignal` ("keep false for ANE→Metal on physical hosts") — implying the default
eval fencing is IOSurface IOFences and shared events are opt-in. On-disk `strings` finds neither key
(shared-cache stub); the in-process hunt is Lane A3 of EXP-025.

### 3.13 The compiler's model.src is a cache package, not a file (2026-10-08, M5 Max, macOS 27.0.1, EXP-026 SU)

The sudo-window hunt for a `model.src` TEXT in the ANECompilerService sandbox was chasing the wrong
object: for the CoreAI/MPSGraph JIT route the compiler runs in-process (ANECompiler.framework is
dlopened in the client — §3.11 family, and EXP-026 v8 watcher saw zero aned activity across two
verified trigger lanes), and everything it consumes and emits persists user-readable under
`~/Library/Caches/coreai-cache/<OSBUILD|pyver>/<proc>/<IDENT64>/<plan-hash64>/`. A plan package
(`*.mpsExecutable.mpsgraphpackage/`) holds: `manifest.plist` (full `compilationDescriptor` JSON +
`deviceDescriptor [0,40,"h17c"]` + `inputShapes`), `original_model_N.mpsgraph` — the model.src
proper, an **MLIR bytecode** container (magic `ML\xefR`, producer `MLIR22.0.0git`, bytecode v6) of
private-`mps`-dialect IR — `specialized_model_N.mpsgraph` (placement-specialized: per-region
`*_ANE_region_*`/`*_GPU_region_*` symbols, `ane_family "A18"`, ANE dtype whitelist text
`fp16,f8E4M3,si8,ui8,si16,ui16`), `binary_0.llir.bundle/h17c/*.mlir.bc` (ANECompiler 10.26.4,
LLIRVersion 0.1b — `anehlo`/`raster`/`llir` dialects, fused `anec.linear`/`anec.swish` kernels),
and on older-keyed entries `binary_0.hwx` — the ANE task binary, freedomtan-format-verified
(magic LE 0xBEEFFACE, CPU 0x0080/0x9, "[H17 (A18 Pro/M5)] Dense HWX", InDim/OutDim + DMA/L2/coeff
tables decode with the vendored `hwx_parsing`). String-dictionary extraction (no dialect
registration needed) yields the full op set and torch-python provenance:
`harness/p2b_mlir_bc_strings.py`. Stock `mlir-opt` parses the container and only fails at private
dialect instantiation. Two measured plans: granite embedding w8 JIT → 13 ANE + 14 GPU regions
(hybrid, `GPU adapter present: NO`); EXP-013 reranker JIT (27.0.1) → specialized-only,
`useANELLIR:false`, no ANE regions. Evidence: `results/EXP-026-ane-kitchen/results/p2b_model_src_*`.

**Attribution (web-check 2026-10-08):** the chain existence is prior art — Apple's own
LLVM *MPS dialect* RFC (2024-02) says MPSGraph is an MLIR dialect consumed as bytecode by
`mpsgraphtool` and handed to "the neural engine compiler"; arXiv:2606.22283 documents
MIL→`anec.*`→hwx formats and the `aned` dispatch broker (the broker part holds for
*execution*; our v8 watcher shows the *compiler* itself runs in-process on the 27.0.1
CoreAI route). Ours, with zero hits in that paper's 302 pages and the wider web: the
`coreai-cache` contents themselves — `ane_family`, the placement plan metadata, hybrid
region counts, `Perf_State` counter semantics, and per-tile matmul2d joules.

### 3.14 Public specialization levers + the write-side placement surface (2026-10-08, web-check + measured)

What Apple now **documents** about the machinery this file spent months prying open —
register before anyone "discovers" it again:

* `AIModel` (CoreAI) *specializes* a `.aimodel` per device+OS and caches the artifact;
  cached copies are invalidated on **OS update** (matches our `<OSBUILD>` cache path
  keys), on source-model change, and under storage pressure unless `.persistent`
  [DOC — developer.apple.com CoreAI "Managing model specialization and caching"].
* `SpecializationOptions(preferredComputeUnitKind:)` / `.cpuOnly` and
  **`expectFrequentReshapes = true`** — the documented answer to per-shape re-specialization
  cost we measured as ~140 ms re-plan on weight-edit reload (API-123/AN-STALE context);
  relevant to every dynamic-shape serving stack on this box [DOC].
* `AIModel.specialize(contentsOf:options:cache:cachePolicy:)` + `model.bookmarkData` /
  `AIModel(resolvingBookmark:)` + `AIModelCache(appGroup:)` — explicit control of *when*
  specialization runs and how cached artifacts outlive the source file [DOC].
* `/usr/bin/mpsgraphtool convert -coremlpackage <pkg> -specializeForDevice` emits the same
  `original_model_N.mpsgraph` / `specialized_model_N.mpsgraph` naming as the closed
  coreai-cache, carries the `placement`/`gpu`/`stitched` dialect grammar, stamps this
  machine's ANE target `mps.aneArch h17c` and `mps.deviceGPUCoreCount`, exposes
  `mps.aneEnableFWToFWSignal` (attribute form of the `kANEFEnableFWToFWSignal` key hunted
  in P2-C3) among ~25 `mps.*` knobs, and repeats the ANE dtype whitelist **byte-equal** to
  the string our cache decode extracted [MEASURED — `results/EXP-027-nax/results/p27_mpsgraphtool_write_side.txt`].
  This turns the private format into a **write-side experimental lane**: hand-built graphs
  can be fed through a public tool and their placement read back with our own reader.

```jsonl
{"id": "API-132", "claim": "Apple now documents the specialization-cache machinery our private decoding mapped: AIModel specializes .aimodel per device+OS, cache keys invalidate on OS update (matching the observed <OSBUILD> path component), with SpecializationOptions.preferredComputeUnitKind/.cpuOnly, expectFrequentReshapes to skip per-shape specialization, AIModel.specialize AOT control, bookmarkData/AIModel(resolvingBookmark:) to serve from cache after deleting the source, and app-group shared caches.", "kind": "fact", "confidence": "documented", "source": "https://developer.apple.com/documentation/coreai/managing-model-specialization-and-caching", "source_type": "primary", "retrieved": "2026-10-08", "updated": "2026-10-08", "topic": ["api", "cache", "specialization"], "entities": ["AIModel", "SpecializationOptions", "AIModelCache", "expectFrequentReshapes"], "evidence": "web-check 2026-10-08 SearXNG/mini fetch", "caveat": "doc-level; measured re-plan cost on this box (~140 ms, AN-STALE) suggests expectFrequentReshapes deserves a measured A/B on dynamic-shape serving", "contested": false}
{"id": "API-133", "claim": "/usr/bin/mpsgraphtool (macOS 27.0.1) is a PUBLIC writer of the private compiler's own bytecode: convert -coremlpackage X -specializeForDevice emits original_model_N.mpsgraph + specialized_model_N.mpsgraph (same naming as coreai-cache), parsing with our MLIR-bytecode reader (producer MLIR22.0.0git, v6), and its string dictionary exposes the placement grammar (placement/gpu/region_call/stitched/memref_backed), this device's ANE target string h17c (mps.aneArch), mps.deviceGPUCoreCount, mps.aneEnableFWToFWSignal (the kANEF knob as a dialect attribute), ~25 further mps.* knobs, and the ANE dtype whitelist string byte-equal to the coreai-cache extraction; minilm specializes to a single main_GPU_region_0 — matching every measured GPU-routing row for that model.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-027-nax/results/p27_mpsgraphtool_write_side.txt", "source_type": "our-own", "retrieved": "2026-10-08", "updated": "2026-10-08", "topic": ["compiler", "mlir", "placement", "tooling"], "entities": ["mpsgraphtool", "h17c", "mps.aneArch", "p2b_mlir_bc_strings"], "evidence": "round-trip on models/minilm128.mlpackage 2026-10-08, both with and without -specializeForDevice; header hex + full string dumps in evidence file", "caveat": "no binary_0.hwx/LLIR emitted via this route yet (likely needs -aimodel/ODIE input); attribute VALUES live in the IR section, still gated on the DialectPlugin stub", "contested": false}
{"id": "API-134", "claim": "Multi-tile matmul2d on M5-class hardware works in public code: MetalHLO (Apache-2.0, commit 44b3a04b) generates MPP kernels using mpp::tensor_ops::matmul2d with execution_simdgroups<8> at 128x128 tiles / 256 threads (64-tile / 4-simdgroup variant for low-occupancy shapes), dextents and slice in (cols, rows) inner-stride-first order, MSL 4.0 + Apple9, plain MTLBuffers with no MTLTensor host API, bundling MLX's gemm_nax cooperative-tensor path — while our coreai-compiler-route harness drops every tilegroup but the first (R8): the wall is route/harness-specific, not a silicon gate. Clone built HERE @44b3a04 (hub tools/vendor, gitignored): swift build FAILS CLT-only (unable to spawn process 'metal' at the vendored mlx-swift CompileMetalFile step) and PASSES under DEVELOPER_DIR=/Applications/Xcode.app (792/792, ~19 s), and our single-tile matmul2d probe MSL compiles to AIR with -std=metal4.0 — the NX-B 'no matmul2d headers' state is CLT-specific: the Xcode 27 SDK ships MetalPerformancePrimitives.framework/Headers/MPPTensorOpsMatMul2d.h.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-027-nax/raw/research-2026-10-08/metalhlo_codegenerator_mpp_matmul_template.txt + results/p27_r8_ladder.txt + results/p27_metalhlo_build.txt", "source_type": "secondary", "retrieved": "2026-10-08", "updated": "2026-10-08", "topic": ["nax", "matmul2d", "compiler", "routing"], "entities": ["MetalHLO", "MLX", "gemm_nax", "matmul2d", "R8"], "evidence": "their benchmarks (GEMM 4096^2 0.91x MLX, M5 Pro; ResNet18 8.7x vs JAX-CPU) + extracted kernel templates; our R8 ladder in the same file set; line-indexed recipe (CodeGenerator.swift :3945/:4013/:4030-4034/:4395-4431/:4466-4490/:4595-4619/:7091-7134) in NAX-SUBMIT.md", "caveat": "their measurements are theirs; our reproduction is the R8 rerun pending a quiet window — recipe extracted and compile-probed here, dispatch not yet re-run", "contested": false}
{"id": "API-135", "claim": "Public Core AI Swift API prints this machine's private arch name: AIModel.deviceArchitectureName == 'h17c' on M5 Max (26A434, unprivileged, no decoder); ComputeUnitKind.availableKinds == cpu,gpu,neuralEngine. The specialization manifest in ~/Library/Caches/coreai-cache/26A434/<proc>/<modelHash>/<optsHash>/.../mpsExecutable.mpsgraphpackage/manifest.plist carries the full compiler descriptor as JSON: deviceDescriptor [0, 40, 'h17c'], allowedComputeDevices 7, preferredDevice 2, enableANECValidationWorkflow true, useANELLIR false, aneCompilerSpatialSplitting 3, enableANECHWRankPromotion true, compilerOptions 1691023, inputShapes, per-arch ANERegionsHash, entry-function attrs mps.aneAlignedIO/mps.disablePreAllocate/mps.disableNDX, Package Version 7.0.63.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-028-apple-tracer/results/e1_public_log_findings.txt + raw/p28_e1_anec/int8_ne_manifest_dump.txt", "source_type": "our-own", "retrieved": "2026-10-08", "updated": "2026-10-08", "topic": ["coreai", "public-api", "cache", "placement", "tooling"], "entities": ["AIModel.deviceArchitectureName", "h17c", "coreai-cache", "manifest.plist", "mps.disableNDX"], "evidence": "harness stdout on every p28_run_bin arm; manifest + mpsgraph archived from the neuralEngine plan of deep_int8 (9e4e68a7.../6C51FA69...)", "caveat": "deviceDescriptor second field (40) uninterpreted — do NOT read as GPU core count (h17c=32 triple-sourced row stands); descriptor values are the compiler's view at specialize time", "contested": false}
{"id": "API-136", "claim": "Unprivileged public os-log gives lane fingerprints for the Core AI runtime: GPU/ANE-preference arms emit in-process com.apple.metalperformanceshadersgraph events (MPSGraph_Delegate 'Delegate init (URL) with resource file:///Users/.../coreai-cache/26A434/p28-run-bin/<modelHash>/<optsHash>/...' UNMASKED — public hook straight into our SU plan decoder; per-batch 'MPSGraphDelegateKernel.coreAI_prepare caching new IO buffers'), CPU arm emits zero MPSGraph events (BNNS delegate confirmed by absence + BNNS dir in plan tree); com.apple.coreai/runtime lifecycle lines 'Model at <url> has been specialized into AIModelCache.default' / 'Loading function'. Cache identity measured live: optsHash is options-keyed and model-independent (same 6C51FA69 across deep_fp16 and deep_int8 neuralEngine; distinct per default/gpu arm), modelHash content-keyed (salting a bundle file leaves hash unchanged). With fp32 I/O every preference places region_type<GPU> — the ANE dtype gate (MEASURE-085/086) reproduces through the fully public path; per-dispatch op signposts are not published at default level.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-028-apple-tracer/results/e1_public_log_findings.txt + raw/p28_e1_smoke/ + raw/p28_e1_anec/", "source_type": "our-own", "retrieved": "2026-10-08", "updated": "2026-10-08", "topic": ["coreai", "logging", "routing", "cache", "placement"], "entities": ["com.apple.metalperformanceshadersgraph", "MPSGraph_Delegate", "AIModelCache.default", "optsHash", "BNNS"], "evidence": "4-arm matrix captured twice (raw/p28_e1_smoke, raw/p28_e1_signpost), delegate-init URLs cross-checked against decoded plan dirs on disk", "caveat": "anec Target Architecture validation lines need sudo log config private:on (kept as declared gap); fingerprint is delegate-granular, not per-op", "contested": false}
{"id": "API-137", "claim": "Espresso ANE eval (0.4 ms median, ANEModelCompilerClient + IOSurface map, no CoreAI/MPSGraph in process) moves 28 ANE enginemon USER-mode channels on M5 Max: PMP0 AF BW and DCS BW ANE L0/L1 RD/WR (50841 ev each) + ANS RD/WR (12146), SOC Floor ANE-LNK0/1-AF-BW + ANS-DMA-AF-BW + ANS-NAND-AF-BW, DCS Floor ANE-DCS-BW + ANS-DCS-BW, SOC-NI6 ANS NAN/RAI/RAO/SL, SOC-NI8 ANE UP, SOC-NI9 ANEXL U — the AN-POS lenses attribute cleanly with zero GPU compute workload; simultaneously AGX UT Engagement perf-state counters tick (PS13 dominant) and GPU power-state residency fills, because the harness creates a Metal device + IOSurfaces: the ANE surface rendezvous keeps the GPU domain warm even for an ANE-only workload.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-028-apple-tracer/results/e3_e4_wire_findings.txt + raw/p28_e3/analysis_es_vs_idle.txt", "source_type": "our-own", "retrieved": "2026-10-08", "updated": "2026-10-08", "topic": ["ane", "observability", "power", "iosurface", "nax"], "entities": ["enginemon", "SOC-NI9 ANEXL U", "SOC-NI6 ANS", "ANE L0", "AGX UT Engagement", "mapIOSurfaces"], "evidence": "enginemon 2.1 --all census: idle1 8s / es_load 30s@250ms during 45 es_harness processes / idle2 8s; delta diff in analysis file", "caveat": "energy windows untouched (no mJ claims; GPU Energy nJ aggregate treated as artifact); attribution is window-level not per-eval", "contested": false}
{"id": "API-138", "claim": "Across two boxes on the same OS build (26A434) the ANE architecture identity is: the compiler target AIModel.deviceArchitectureName — corroborated by /usr/bin/mpsgraphtool -specializeForDevice mps.aneArch and enforced by the Core AI AOT gate, which accepts exactly one target per box — reads h17c on the M5 Max (Mac17,14, boardType 544) and h16g on the M4 mini (Mac16,10, boardType 256), while the private _ANEDeviceInfo.aneArchitectureType selector returns the g form on both (h17g, h16g), agreeing with the compiler target on the M4 but diverging on the M5 Max; both observed parts contradict the resolver-derived rows of arXiv 2606.22283 ch34 Table 34.3 (M4 base -> h16 vs observed h16g; M5 Pro/Max -> h17s vs observed h17c), and coreai-build rejects the bare base target name h16.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-028-apple-tracer/results/e6_arch_surface_reconcile.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["hardware", "attribution", "compiler", "cross-chip", "private-api"], "entities": ["h17c", "h16g", "h17g", "_ANEDeviceInfo", "deviceArchitectureName", "mpsgraphtool", "Mac17,14", "Mac16,10", "incompatibleCompiledAssetArchitecture"], "evidence": "four-surface read (device-info selector, mpsgraphtool mps.aneArch, AIModel.deviceArchitectureName, AOT acceptance gate) on two hosts: M5 Max accepts only h17c of 21 built targets, M4 mini only h16g of 5 built targets, each rejection naming device+asset", "caveat": "two parts only (M4 base, M5 Max), one OS build 26A434; M4 Pro/Max and M5 base/Pro untested; mini R2 taken from -aimodel because the fp32 minilm coremlpackage fails ANE validation (Code=53); rejected assets are our own well-formed AOT builds; the private selector g-form persistence is observed on two parts only; prior-art per SOURCES.md 'Novelty check 2026-10-10': the arch-tracks-device-identifier rule and the single-matching-arch load behaviour are already public (LANDSCAPE-072) — our novelty is the observed parts and the private-selector divergence; the M4 half is our own merged prior art (john-rocky/coreai-model-zoo PR #36, LANDSCAPE-076)", "contested": false}
{"id": "API-139", "claim": "Core AI cache keys split into modelHash64 (lowercase hex, per model — 175 distinct across the cache) and optsHash64 (uppercase hex, osbuild layout only, absent in the pyver layout), where optsHash is a pure function of the compute-unit SpecializationOptions and model-independent: 6C51FA69… = neuralEngine (preferredDevice 2 / allowedComputeDevices 7, reused across 10 distinct models), 14371356… = cpu-only (preferredDevice 1 / allowedComputeDevices 1, 9 models), 3EED3375… = mixed/default (1,2 / 1,7, 8 models); all 198 decoded plans carry arch stamp h17c, completing the live-log reading of API-136 from disk and confirming the same optsHash is model-independent.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-026-ane-kitchen/results/coreai_cache_keys.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["coreai", "cache", "keys", "specialization"], "entities": ["modelHash64", "optsHash64", "SpecializationOptions", "preferredDevice", "allowedComputeDevices", "coreai-cache"], "evidence": "bench/coreai_cache.py census: 198 plans (osbuild 33 / pyver 165); optsHash grouped by descriptor preferredDevice/allowedComputeDevices/useANELLIR", "caveat": "one machine/OS build (26A434); the mapping of numeric device masks to named arms is inferred from preferredDevice/allowedComputeDevices; the pyver layout carries no optsHash directory", "contested": false}
{"id": "API-140", "claim": "PMP0/SOC-NI Util BW/SOC-NI9 'ANEXL U' is promoted to a calibrated, unprivileged, lane-exclusive ANE metric on M5 Max: it reads zero in every non-ANE window (idle x2, GPU x2, CPU) and ~19600 with <0.2% spread in both ANE windows of a matched matrix running the same full-ANE-region model on ANE/GPU/CPU (76.5 / 26.8 / 213.0 ms per pair), while SOC-NI8 'ANE UP' is near-exclusive (~18400 ANE vs 13 GPU, 0 idle/CPU) and the PMP0 DCS+AF ANE L0/L1 lanes are confirmed NON-exclusive (35.3k ANE vs 21.7k GPU = 1.6x).", "kind": "measurement", "confidence": "measured", "source": "results/EXP-027-nax/results/p27_anpos_promote.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["attribution", "counters", "ane", "observability"], "entities": ["SOC-NI9 ANEXL U", "SOC-NI8 ANE UP", "enginemon", "PMP0", "M5 Max"], "evidence": "matched matrix via harness/p27_anpos_promote.sh (same iters per lane, enginemon --all 500 ms); window files raw/promote/*.jsonl; ABC analyzer results/p27_anpos_promote_analyze.py", "caveat": "one machine/OS build 26A434; n=2 idle/GPU windows and n=1 CPU control; ANE arm is the JIT route on one graph; attribution is window-level not per-eval; prior-art per SOURCES.md 'Novelty check 2026-10-10': ANEXL/ANE-UP are already read publicly by aneperf by channel name (LANDSCAPE-073) and ANE power by SiliconScope (LANDSCAPE-074), and the community holds ANE utilization unobtainable (LANDSCAPE-075) — the lane-exclusivity/calibration is the new part", "contested": false}
{"id": "API-141", "claim": "The ANE↔GPU direct-link wire (the kernel shared-event counter over IOSurfaces, API-102/103) carries DATA as well as sync, bidirectionally and repeatably on M5 Max: a standalone harness using only public Metal plus the runtime-only IOSurfaceSharedEvent has the GPU compute kernel write a per-iteration pattern into an IOSurface and signal, and the ANE-side wrapper waits and the CPU verifies the surface content — 500/500 iterations verified in BOTH directions at median 123 µs (GPU→wrapper) and 136 µs (wrapper→GPU), unprivileged, no private ANE framework in the harness.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/chain_harness.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["ane", "gpu", "sync", "iosurface", "chaining"], "entities": ["MTLSharedEvent", "IOSurfaceSharedEvent", "IOSurface", "chain_harness", "MTL4CommandQueue"], "evidence": "harness/chain_harness.m run 500 and 200 iterations; per-iteration surface-content verification (BGRA8 shader-R byte), zero mismatches; port = MTLSharedEventHandle.eventPort wrapped to initWithMachPort:", "caveat": "demonstrates the PRIMITIVE chain (Metal GPU ↔ IOSurfaceSharedEvent wrapper), which is the wire the ANE uses; it does NOT put a running ANE program on the other end — that integration remains blocked (Path-A crash on attached _ANESharedEvents; Path-B shared-event SIGSEGV, F-40). iOSurface texture from a non-ANE-assumed pixel format: the shader R component lands in memory byte 2 (expectation fixed accordingly)", "contested": false}
{"id": "API-142", "claim": "Interposing the shipping Core AI stack (DYLD_INSERT_LIBRARIES over the public runner) shows it creates one IOSurfaceSharedEvent mach-port counter per ANE region (13 for the granite h17c plan) and signals each once per eval (260 signals = 13 x 20, values 2..40), and a duplicate wrapper over one port observed the live signaled value afterwards (we joined the counter) — BUT the wiring is arms-invariant (identical under cpuOnly, gpu, neuralEngine and default) and -[_ANERequest setSharedEvents:] fires zero times, so these are generic MPSGraph/Metal-side counters, NOT the ANE route; Core AI's ANE execution does not use the _ANERequest shared-event route.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/join_chain.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["ane", "gpu", "sync", "coreai", "interposition"], "entities": ["_ANERequest", "IOSurfaceSharedEvent", "Core AI", "MPSGraph", "join_chain.dylib"], "evidence": "harness/join_chain.dylib over p28_run_bin on granite97m_fp16_s128.h17c.aimodelc, 20 evals x 4 arms; SUMMARY lines recorded in the results file", "caveat": "one machine/OS build; the arms-invariant count is why the shared events are declared generic; the ANE-specific e5rt/E5 route belongs to Core ML's ANE execution and was not reachable (no ANE-routed .mlmodelc on this box)", "contested": false}
{"id": "API-143", "claim": "Core ML is the ANE-specific shared-event route and Core AI is not: with a conv graph that Core ML places on the ANE (conv_512x64_d8.mlpackage — 8x fp16 conv [1,512,1,64]; ANEXL U = 18271 over 100k predictions), interposition shows -[_ANERequest setSharedEvents:] fires 101 times (all nil) and 0 IOSurfaceSharedEvent are created, whereas on the same box through Core AI on an ANE model the same hook fires 0 times while 13 generic counters are created and signalled (arms-invariant, API-142) — so Core ML drives the ANE through _ANERequest; but a pure-ANE workload attaches NO events, so a live non-nil inter-engine chain needs a mixed ANE+GPU model.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/coreml_ane_route.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["ane", "gpu", "sync", "coreml", "coreai", "interposition"], "entities": ["Core ML", "Core AI", "_ANERequest", "IOSurfaceSharedEvent", "conv_512x64_d8.mlpackage"], "evidence": "harness/coreml_run.m under enginemon (ANEXL) and under join_chain.dylib; the Core ML vs Core AI comparison table in the results file", "caveat": "one machine/OS build; the nil events are model-specific (pure ANE); the designated initializer was not hooked, so creation-time events are not excluded", "contested": false}
{"id": "API-144", "claim": "The ANE-side inter-engine event object is real and capturable during Core ML ANE execution: with the interposer extended to the event-creation path, every _ANERequest for the ANE-placed conv model is created with a NON-NIL _ANESharedEvents (the getter returns non-nil 2/eval) carrying a _ANESharedSignalEvent bound to an IOSurfaceSharedEvent counter (401 signal events over 200 preds; 1 distinct counter reused; value 0 at bind; symbolIndex 255, agentMask all-ones), while Core AI attaches none — and the counter is not built via initWithMachPort nor signalled via the ObjC setter, so the write is hardware/firmware-side.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/ane_event_joined.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["ane", "gpu", "sync", "coreml", "interposition"], "entities": ["_ANERequest", "_ANESharedEvents", "_ANESharedSignalEvent", "IOSurfaceSharedEvent", "Core ML"], "evidence": "harness/join_chain.dylib (creation-path hooks) over coreml_run on conv_512x64_d8.mlpackage, 200 predictions; SUMMARY + capture lines in the results file", "caveat": "one machine/OS build; the counter's value change during execution was not observed (write is hardware-side; the object is released by exit) — polling a retained/duplicated wrapper is the next slice", "contested": false}
{"id": "API-145", "claim": "The ANE-side shared-event attached to every Core ML ANE request is INERT for a single-engine workload: retaining the captured counter and polling it at ~5000/s across 5000 predictions of the ANE-placed conv model shows only one distinct signal value (0) and the counter never moves (samples=7124, distinct=1, final=0), despite 5001 request inits each carrying a signal event — so the object is present and capturable but not armed, and a live cross-engine handoff (and thus any GPU-side counterpart) requires a genuinely partitioned ANE+GPU model.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/ane_event_joined.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["ane", "gpu", "sync", "coreml", "interposition"], "entities": ["_ANESharedSignalEvent", "IOSurfaceSharedEvent", "signaledValue", "Core ML", "conv_512x64_d8.mlpackage"], "evidence": "join_chain.dylib with a retained-counter poll thread over coreml_run 5000 predictions; SUMMARY + POLL lines in the results file", "caveat": "one machine/OS build; 'never moves' is measured on this pure-ANE model only — a partitioned model, or a hardware-side write not surfaced through the ObjC signaledValue accessor, would need a separate test", "contested": false}
{"id": "API-146", "claim": "A genuinely partitioned local model exists (FluidAudio parakeet-tdt Encoder: MLComputePlan shows 1381 ANE + 4 CPU ops), yet Core ML still does not ARM the shared events: running it, every request carries a signal event with value 0 and NONE of the 8 captured counters moves across 22,715 polls; with compute_units=all the same Encoder is placed ENTIRELY on the GPU (1385 GPU, no ANE) — so Core ML does not co-schedule ANE+GPU on this box, the only split is ANE+CPU, and the live ANE↔GPU shared-event handoff stays unobserved with the available models.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/coreml_partition_no_arm.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["ane", "gpu", "coreml", "placement", "sync"], "entities": ["parakeet-tdt Encoder", "MLComputePlan", "_ANESharedSignalEvent", "IOSurfaceSharedEvent", "FluidAudio"], "evidence": "coremltools MLComputePlan over the local FluidAudio model set; join_chain.dylib retain-and-poll (8 counters, 22715 samples) on Encoder.mlmodelc, 30 predictions", "caveat": "one machine/OS build; 'not armed' covers the local model set (FluidAudio, bench zoo, Core AI); an Apple system model genuinely partitioned ANE+GPU was not runnable here with known inputs", "contested": false}
{"id": "API-147", "claim": "Core ML's placement heuristic, read through MLComputePlan (per-op device + the planner's own MLComputePlanCost.weight), has three observable properties on M5 Max: compute_units CAPS the candidate set (cpu->CPU, gpu->GPU, neuralEngine/all->prefer ANE); fp16 is a gate (fp32 convs fall to CPU); and a conv is ANE-placed only above ~1.5e8 FLOPs (~7.5e7 MACs) — a COMPUTE threshold, since it scales with kernel area (k=3 flips between 74.6M and 78.0M MACs, k=5 between 74.6M and 80.3M MACs; the bracket is FLOPs (149.3,156.0]M). At the tested sizes conv1x1, pooling and linear did not reach ANE.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/coreml_route_sweep.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["coreml", "placement", "routing", "heuristic"], "entities": ["MLComputePlan", "MLComputePlanCost", "conv2d", "fp16", "M5 Max"], "evidence": "harness/coreml_route_sweep.py: base one-axis sweep + conv C/H threshold grid + kernel-size dependence probes (k=3/5/7) with MACs/FLOPs brackets", "caveat": "single-op models on one OS build; multi-op boundary costs unmeasured; the ~150 MFLOP bound is a bracket; this is the planner's DECISION, not runtime confirmation; refined by API-156 - the bound is CONFIG-SPECIFIC (FLOPs alone does not determine the decision) - and by API-158: placement is decided at the GRAPH level (no mixed graphs; a 6-conv graph of 9.4e6-MAC convs is all-ANE while a single 7.1e7-MAC conv is CPU), so this single-op bound does not predict multi-op models", "contested": false}
{"id": "API-148", "claim": "Core ML's planned placement is honoured at runtime for the conv threshold: a just-below / just-above fp16 conv3x3 pair (C=352, 71.4M MACs, plan CPU vs C=384, 84.9M MACs, plan ANE) run 20000 predictions each with the ANE-exclusive lens reading ANEXL U = 0 for the below model and 12065 for the above model — so above ~1.5e8 FLOPs the conv actually executes on the ANE and below it there is no ANE activity, with no silent fallback observed for this case.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/coreml_route_sweep.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["coreml", "placement", "routing", "validation"], "entities": ["MLComputePlan", "conv2d", "ANEXL U", "enginemon", "coreml_run.py"], "evidence": "enginemon --all over harness/coreml_run.py (coremltools) on the route_below/route_above mlpackages, 20000 predictions each; ANEXL/ANE-UP totals in the results file", "caveat": "one machine/OS build; single-op models; the ObjC coreml_run.m was unusable for mlprogram models (zero-shape input) and its first reading was discarded as compile-side", "contested": false}
{"id": "API-149", "claim": "Core ML's placement code is reachable for RE despite having no on-disk binary (the framework file is a broken symlink; the code is in the dyld shared cache and dyld_info cannot target a single cache image): reading the LOADED image at runtime (_dyld_get_image_header + slide, parse LC_SEGMENT_64) and disassembling bytes at a method IMP with llvm-mc works unprivileged, and the routing entry points are -[MLComputePlan computeDeviceUsageForMLProgramOperation:] @0x191f7c2a8, -estimatedCostOfMLProgramOperation: @0x191f7ab84, +[MLComputePlan computePlanOfModelStructure:modelAsset:configuration:error:] @0x191f7c420 and -computeDeviceUsageForNeuralNetworkLayer: @0x191f7bab8; a constant search for 1.5e8/1e8/2e8/7.5e7 as float32/double/int32/int64 found NOTHING in __TEXT or __DATA_CONST (only __LINKEDIT 4-byte noise), so the ~1.5e8-FLOP conv threshold is computed rather than a literal constant and must be recovered from the instruction stream.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/coreml_plan_recon.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["coreml", "placement", "reverse-engineering", "tooling"], "entities": ["CoreML.framework", "MLComputePlan", "dyld shared cache", "llvm-mc", "_dyld_get_image_header"], "evidence": "harness/coreml_image_probe.m (runtime image parse + constant search + method IMPs) and llvm-mc disassembly of the computeDeviceUsage function; segment table and first instructions in the results file", "caveat": "one machine/OS build; the constant search covered the listed values only; a full policy reversal (which fields the function reads, what it computes) is not done", "contested": false}
{"id": "API-150", "claim": "A guided walk of Core ML's placement code from -[MLComputePlan computeDeviceUsageForMLProgramOperation:] resolves the call graph and data references (BL targets, ADRP+ADD to strings/tables) in the mapped image, but a depth-3/40-function walk finds NO movz/movk pair building ~1.5e8 (or 7.5e7/1e8/2e8) as an integer and the byte search found no float/double/int literal in __TEXT/__DATA_CONST — so the ~1.5e8-FLOP conv placement threshold (API-147) is DERIVED from other fields (cost weights/shapes/ratios), not stored as a constant; a naive whole-__TEXT MOVZ/MOVK adjacency scan is too noisy to substitute for a decompiler, which is what full recovery needs next.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/coreml_plan_recon.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["coreml", "placement", "reverse-engineering"], "entities": ["MLComputePlan", "coreml_walk.m", "movz", "movk", "dyld shared cache"], "evidence": "harness/coreml_walk.m walking 0x191f7c2a8 depth 3 over 40 functions (6653 disassembled lines); resolved BL/ADRP+ADD targets; no threshold-building movz/movk found", "caveat": "breadth-limited walk; negative result covers the reachable set only; a directed walk from estimatedCostOfMLProgramOperation: or a decompiler on the extracted cache image is untried", "contested": false}
{"id": "API-151", "claim": "Core ML's placement code is fully disassemblable unprivileged with the Homebrew 'ipsw' tool: the cache-only CoreML image extracts to a real Mach-O (ipsw dyld extract) and cache addresses disassemble with labels (ipsw dyld disass --vaddr), and at -[MLComputePlan computeDeviceUsageForMLProgramOperation:] (0x191f7c2a8) the path performs double-precision comparisons (fcmp d0,#0.0 / b.hi / csel) rather than integer-threshold tests — consistent with API-150's conclusion that the ~1.5e8-FLOP conv gate is DERIVED from cost weights, not a stored constant.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/coreml_plan_disasm.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["coreml", "placement", "reverse-engineering", "tooling"], "entities": ["ipsw", "MLComputePlan", "dyld shared cache", "fcmp", "computeDeviceUsageForMLProgramOperation:"] , "evidence": "ipsw dyld extract of CoreML + ipsw dyld disass at 0x191f7c2a8 and 0x191f7ab84; fcmp/csel comparisons in the device-usage path (results file)", "caveat": "one machine/OS build; the disassembly is a bounded window, not a full function or call-graph analysis; cost-weight semantics still to be read out; SUPERSEDED on the floating-point point by API-153: the ipsw --vaddr space differs from the runtime address space, and the correct runtime bytes of this path contain no fcmp", "contested": true}
{"id": "API-152", "claim": "Core ML's placement call path is traced from the runtime entry points: -[MLComputePlan computeDeviceUsageForMLProgramOperation:] is a wrapper that extracts op attributes, calls sub_191F7ADB4 (the cost region reached from estimatedCostOfMLProgramOperation) and then sub_191F7BC30 to build the result; sub_191F7BC30 switches on a compute-unit enum via `switch(sub_65408860(v0))` with cases 1/2/4 (power-of-two unit masks, parsimoniously CPU/GPU/NeuralEngine), selects a distinct string constant per case, has NO floating-point comparison (only integer sentinel 0x7fffffffffffffff and a bit-mask filter) and returns a dictionary object; the exact predicate mapping cost to the chosen unit lives in the callers, not in these wrappers.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/coreml_plan_callpath.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["coreml", "placement", "reverse-engineering"], "entities": ["MLComputePlan", "sub_191F7BC30", "sub_191F7ADB4", "computeUnitMask", "completion"], "evidence": "runtime byte dumps of 0x191f7c2a8 / 0x191f7ab84 / 0x191f7bc30 -> llvm-mc disassembly -> LLM-assisted decompilation checked against the listing; the enum switch and the wrapper structure are in the listing", "caveat": "one machine/OS build; 1/2/4 -> CPU/GPU/ANE is inferred, the case string contents were not resolved; and ipsw's --vaddr space differs from runtime addresses (a first ipsw-based decompile hit BLAS code and was discarded)", "contested": false}
{"id": "API-153", "claim": "CORRECTION + structural map for Core ML placement: API-151's 'double-precision comparisons in the device-usage path' was an address-space artifact of `ipsw dyld disass --vaddr` (its vaddr space != the runtime address space); on the correct runtime bytes -[MLComputePlan computeDeviceUsageForMLProgramOperation:] @0x191f7c2a8 contains NO floating-point instruction at all (no d0/s0 access), and across the examined cluster only the estimatedCost wrapper has a single float op (fcmp d0,d0 NaN check). A reverse-reference scan (new harness/coreml_findcallers.m: BL/B sites by target + 8-byte pointer-table matches in readable segments) shows sub_191F7ADB4 is its OWN function (prologue sub sp,sp,#432) that orchestrates tag-keyed dictionary lookups over type tags {1,2,4,5,6} with no accumulation and no cost comparison; sub_191F7BC30 (compute-unit enum switch case 1/2/4) is called only from 0x191f7bb60 and 0x191f7c358; and the ObjC method IMPs 0x191f7ab84/0x191f7c2a8 have NO direct BL callers (reached via objc_msgSend). So the functions reachable from the two ObjC entry points are attribute plumbing and per-unit configuration lookup; the numeric cost/selection work is delegated to unread callees.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/coreml_plan_callpath.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["coreml", "placement", "reverse-engineering", "correction"], "entities": ["ipsw", "coreml_findcallers.m", "sub_191F7ADB4", "sub_191F7BC30", "objc_msgSend"], "evidence": "correct runtime dumps of 0x191f7c2a8/0x191f7ab84/0x191f7adb4/0x191f7bc30 -> llvm-mc with float-op counts (0/1/0/0 fcmp); coreml_findcallers.m reverse scan reporting 2 call sites into sub_191F7BC30 and 0 into the method IMPs", "caveat": "one machine/OS build; a static scan cannot see objc_msgSend callers, so the decision may live in ObjC plan-assembly rather than C++ code (that is the open question); the cluster examined is the reachable set from the two entry points", "contested": false}
{"id": "API-154", "claim": "Core ML's plan API on macOS 27 (SDK 27): the ObjC entry is the ASYNC +[MLComputePlan loadContentsOfURL:configuration:completionHandler:] (the synchronous +computePlanWithContentsOfURL:configuration:error: no longer exists; the private +computePlanOfModelStructure:modelAsset:configuration:error: sits behind it), devices are id<MLComputeDeviceProtocol> (there is NO MLComputeDevice class), and program.functions is a name->function dictionary (no functionName property) - so the pack's coreml_plan.m neither compiles nor runs on this SDK until fixed (it is fixed now, with a no-ARC retain gotcha: the completion-handler argument is borrowed, so `plan = p` leaves a dangling pointer and the next [plan modelStructure] segfaults in objc_msgSend). MLComputePlanDeviceUsage privately exposes -deviceSupportInfoArray and -supportInfoForComputeDevice: returning MLComputePlanDeviceUsageSupportInfo objects with ivars _state (int64) and _computeDevice; at BOTH sides of the placement threshold (conv 1.89e7 FLOPs -> CPU preferred, 1.21e9 -> ANE preferred) the support state is 0 for CPU and ANE alike and both devices are supported - so the preference is NOT an eligibility/support gate but an internal cost/perf choice; estimatedCostOfMLProgramOperation: returns an MLComputePlanCost whose weight is normalised (1 for a single-op model), so the API exposes the decision, not the comparison.", "kind": "fact", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/coreml_plan_flip.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["coreml", "placement", "api", "tooling"], "entities": ["MLComputePlan", "loadContentsOfURL:configuration:completionHandler:", "MLComputePlanDeviceUsageSupportInfo", "deviceSupportInfoArray", "coreml_plan.m", "plan_devicesupport.m"], "evidence": "harness/plan_devicesupport.m + fixed harness/coreml_plan.m against SDK 27 headers; support-info dumps for the small/large pair (state 0 both sides); lldb backtrace of the no-ARC dangling-plan segfault", "caveat": "one machine/OS build; _state semantics are inferred from observation (0 at both sides) rather than enumerated; the async API is Swift-refined in the SDK docs so the ObjC surface may change again", "contested": false}
{"id": "API-155", "claim": "Core ML's conv placement threshold is independently re-derived with the SDK's own plan API (harness/plan_devicesupport.m, single conv3x3): for C=256 the preferred device flips CPU->ANE between 1.416e8 and 1.557e8 conv FLOPs (H=12,W=10 -> CPU; H=12,W=11 -> ANE; equivalently H=11 1.427e8 CPU vs H=12 1.699e8 ANE at W=H), bracketing theta for this configuration in (1.42e8, 1.56e8) and corroborating API-147's ~1.5e8 gate with an instrument independent of the earlier route sweep.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/coreml_plan_flip.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["coreml", "placement", "threshold"], "entities": ["MLComputePlan", "conv3x3", "conv FLOPs", "plan_devicesupport.m"], "evidence": "flip sweep table in the results file (C=256, H or W varied, preferred device read per model); coreml_plan.m agrees on the small/large pair", "caveat": "measured for C=256 conv3x3 only; no clean FLOPs law across kernel sizes/channel counts, and the exact compared quantity is still unrecovered", "contested": false}
{"id": "API-156", "claim": "Core ML's conv placement preference is NOT a function of conv FLOPs alone: at IDENTICAL 1.4746e8 conv FLOPs - i.e. also identical 7.37e7 MACs, so the counterexample holds in either unit - a k=1 C=256 25x45 conv is ANE-preferred while a k=5 C=128 15x12 conv is CPU-preferred (reproduced 3/3, deterministic). The flip brackets in MACs cluster within ~10% but are not equal (k=1/C=256 ~7.2-7.4e7 MACs, k=5/C=128 ~7.4-7.9e7, k=3/C=64 still CPU at 7.5e7), so the gate is approximately a MACs threshold with mild config dependence. Within a single config the flip is monotone in FLOPs, but the flip FLOPs differ per (k,C): k=1/C=256 flips at <=1.4746e8, k=5/C=128 needs >1.4746e8, k=3/C=64 is still CPU at 1.493e8, k=3/C=512 is still CPU at 1.4156e8 - and the difference tracks neither weight count alone (k=3/C=512 5x6, 2.36M weights, CPU at 1.4e8 vs k=5/C=256 10x11, 1.64M weights, ANE at 3.6e8) nor output count alone (k=1/C=256 25x45, 288k outputs, ANE vs k=3/C=64 45x45, 130k outputs, CPU at HIGHER FLOPs). So API-147's '~1.5e8 FLOPs gate (kernel-scaled)' and API-155's bracket are CONFIG-SPECIFIC correlates, not a law: the planner weights a per-op cost model with inputs beyond FLOPs (weights, activations, shape).", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/coreml_plan_flip.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["coreml", "placement", "threshold", "correction"], "entities": ["MLComputePlan", "conv3x3", "conv FLOPs", "plan_flip_sweep.sh", "kernel size"], "evidence": "one-conv-per-model sweeps across k in {1,3,5} and C in {64,128,256,512} (table in the results file, harness/plan_flip_sweep.sh); the same-FLOPs pair reproduced 3/3 by plan_devicesupport", "caveat": "single-op models only, one OS build: with several ops the planner's cost weights are normalised across the graph, so a multi-op model could decide differently; the counterexample is exact for single-op graphs", "contested": false}
{"id": "API-157", "claim": "Core ML's conv placement gate is ARITHMETIC PLUS a systematic kernel term. Holding conv MACs fixed at 7.4e7 in single-op models, EVERY k=1 config (C=64/128/256/512, spatial 135x134 down to 17x17) is ANE-preferred while EVERY k=3 config (same four channel counts) is CPU-preferred; bisected per config the k=1 threshold is <=7.30e7 MACs (C=192) and (7.21,7.37)e7 (C=256) whereas k=3 crosses higher - (7.47,7.90)e7 at C=192 and (7.14,7.79)e7 at C=256 - so the MACs threshold RISES with kernel size. Practical reading: 1x1 convs -> ANE from ~7.2-7.3e7 MACs (1.44-1.46e8 FLOPs), 3x3 from ~7.5-7.8e7 MACs (1.50-1.56e8 FLOPs), so '~150 MFLOPs' is a good ~+/-10% rule of thumb for the common 3x3 case but not the law. Every simple single-factor metric is refuted by at least one measured row: output count (ANE at 147,968 outputs vs CPU at 129,600), weight count (ANE at 262,144 weights vs CPU at 147,456), spatial size (ANE at 12 vs CPU at 2,025) and arithmetic intensity (ANE at ~32 MACs/element vs CPU at ~252).", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/coreml_plan_flip.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["coreml", "placement", "threshold", "heuristic"], "entities": ["MLComputePlan", "conv2d", "kernel size", "MACs", "plan_mac_probe.py", "plan_hw_sweep.sh"], "evidence": "fixed-MAC grid at 7.4e7 x (k in 1,3,5 x C in 64..512), 12 single-op models, plus MACs bisections for k=1/k=3/k=5 at C=192 and C=256; decisions read by harness/plan_devicesupport.m", "caveat": "single-op models on one OS build; the kernel correction is a few percent and is NOT yet expressed as a formula; multi-op graphs normalise the planner's cost weights and are untested", "contested": false}
{"id": "API-158", "claim": "Core ML placement is a GRAPH-level decision, not a per-op one, and it is NOT predicted by the single-op rule. In a padded conv3x3 C=256 stack (N convs + ReLU, input HxH) the plan shows NO MIXED graph - every op takes one device - and the CPU->ANE boundary is a clean, deterministic, monotone phase diagram in (N, H): ANE first appears at (N=1,H=16), (2,11), (3,8), (4,6), (6,4) while (1,11), (2,8), (3,6), (4,5), (5,4), (5,5) stay CPU (re-runs identical). This contradicts the single-op threshold: a 6-conv graph of 9.44e6-MAC convs (5.66e7 total) is placed ENTIRELY on ANE, yet a SINGLE 7.14e7-MAC conv is CPU - seven times the per-op work. Single-scalar explanations are each refuted by a counterexample pair: total MACs ((6,4) 5.66e7 ANE vs (2,8) 7.55e7 CPU), per-op MACs ((6,4) vs (5,4), same 9.44e6, opposite), N*H ((2,10)=20 ANE vs (5,5)=25 CPU), op count ((5,4)=10 CPU vs (4,6)=8 ANE), weight count (N=5 CPU vs N=6 ANE). The per-op threshold apparently DROPS as layers are added (N=1 ~7.4e7, N=3 ~2.5e7, N=6 <=9.4e6), i.e. the planner trades per-op size against graph length, but no single scalar of (N,H) fits the table. Practical consequence: for real multi-layer models, placement must be READ FROM THE PLAN of the actual model or forced via the compute-unit configuration - the '~150 MFLOPs per conv' rule of thumb is not a predictor.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/coreml_plan_flip.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["coreml", "placement", "heuristic", "graph-level"], "entities": ["MLComputePlan", "conv2d", "plan_devicesupport.m", "make_graph.py", "computeUnits"], "evidence": "phase diagram over N in 1..6 x H in {4,6,8,11,16} plus discriminating points (2,10),(2,12),(3,7),(4,5),(5,5), all read per-op by plan_devicesupport; (5,4) CPU and (6,4) ANE reproduced on re-runs", "caveat": "one OS build; the family is uniform (conv3x3, C=256->256, spatial preserved, ReLU between), so the boundary's exact shape for other channel counts/kernels and for branched graphs is unmeasured; the aggregate the planner minimises is unidentified; the 'no mixed graphs' part holds only for ALL-CAPABLE graphs - a real model splits exactly at ops the device cannot execute (see API-159) and synthetic conv/pool/softmax/topk are all ANE-executable, which is why none of them split", "contested": false}
{"id": "API-159", "claim": "Reconciliation of the mixed-plan contradiction: reading the real local model (FluidAudio parakeet-tdt-0.6b-v3 Encoder.mlmodelc) with the new harness reproduces API-146 exactly - compute_units=cpuAndNeuralEngine gives 1381 ops preferred ANE + 4 ops preferred CPU, and compute_units=all gives 1385 ops GPU + 0 CPU - and the four CPU ops are ios17.cast (x2), ios17.expand_dims and ios17.less, i.e. type/shape plumbing and a comparison producing a boolean mask: exactly the ops the ANE cannot execute. Under 'all' the same ops are GPU, so nothing is left on CPU. The plan therefore splits by a CAPABILITY FILTER (which ops a candidate device can execute), not by cost; where every op is executable, API-158's single-device phase diagram applies to that capable group, and API-158's 'no mixed graphs' is a property of all-capable graphs rather than a general one. Synthetic conv/pool/softmax/topk graphs never split because all of those ops are ANE-executable (even topk is ANE-preferred at 32x32/C=256).", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/coreml_plan_flip.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["coreml", "placement", "capability", "correction"], "entities": ["MLComputePlan", "parakeet-tdt Encoder", "ios17.less", "ios17.cast", "ios17.expand_dims", "plan_devicesupport.m"], "evidence": "plan_devicesupport on Encoder.mlmodelc under both compute-unit settings; per-op operator names of the 4 CPU ops; independent reproduction of API-146's 1381/4 and the all-GPU swap", "caveat": "one machine/OS build; the capability list is illustrated by one model's 4 non-executable ops, not enumerated per op type; what the planner optimises WITHIN a capable group is still open (API-158); REFINED by API-160 - the trigger is the tensor DTYPE (int32/bool data), not the op types named here", "contested": false}
{"id": "API-160", "claim": "What forces an op onto the CPU in an otherwise-ANE plan is the tensor DTYPE, not the op type: the ANE is an fp16 DATA path. Causal A/B with the MIL builder (harness/make_dtype_test.py) - same graph (3 big convs + reduce_mean + cast + expand_dims + less), only the tail dtype changed - gives: fp16 tail => ALL ops ANE; int32 tail => cast(int32), expand_dims(int32) and less go CPU while the convs/reduce stay ANE; and an fp32 export cast stays ANE (so the fp32 output cast is not a CPU cause). This reproduces the real model's split pattern, and the real model's MIL confirms it - the CPU path is the lengths/mask plumbing (cast->int32, expand_dims on int32, less(int32,int32)->bool, expand_dims on bool), while the hundreds of other int32/bool entries in the file are ATTRIBUTES (axes/strides/pads/perms) that are constants and fine. This corrects API-159's phrasing (op types) to the dtype rule. Instrument lesson recorded: a single SMALL op is CPU for size reasons (§6), so an op's device only reads out capability when the model sits in the ANE regime - the naive op battery measured size, not capability.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/coreml_plan_flip.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["coreml", "placement", "capability", "dtype", "correction"], "entities": ["MLComputePlan", "int32", "bool", "fp16", "make_dtype_test.py", "ios17.cast", "ios17.less"], "evidence": "make_dtype_test.py fp16 vs int32 vs fp32 tail (only the dtype differs) read by plan_devicesupport; ops_battery.py 65-op scan in both bare and ANE-regime modes; Encoder.mlmodelc/model.mil plumbing lines", "caveat": "one machine/OS build; the compiled plan is not expected to match the source MIL op-for-op (optimisation passes), so the synthetic A/B is the load-bearing evidence; whether e.g. fp32 data tensors (not just casts) also disqualify an op is untested; the capability rule for other dtype families is unmeasured", "contested": false}
{"id": "API-161", "claim": "The graph-level rule (layer 3) resists both the public cost API and a first code read: (a) MLComputePlanCost.weight is a NORMALISED EQUAL SHARE - in a chain of N identical convs each conv reports 1/N and every relu reports 0 - so the planner's exposed cost carries no decision signal; (b) +[MLComputePlan computePlanOfModelStructure:modelAsset:configuration:error:] @0x191f7c420 is a WRAPPER/VALIDATION path (no loop over operations, no cost comparison, no objc_msgSend selector pattern; it normalises arguments, calls a same-image boolean helper at 0x191f7c848 and delegates outward), so the decision lives in a callee outside that body; (c) an additive cost model (ANE iff SUM(MAC_i) + beta*N >= Theta) is REFUTED by the phase-diagram data - (5,5) CPU and (6,4) ANE force beta > 1.71e7 while (3,7) ANE and (5,5) CPU force beta < 6.5e6 - so the aggregate is not of the additive form tried.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-025-ane-gpu-sync/results/coreml_plan_flip.txt", "source_type": "our-own", "retrieved": "2026-10-10", "topic": ["coreml", "placement", "reverse-engineering", "negative"], "entities": ["MLComputePlanCost", "weight", "computePlanOfModelStructure:modelAsset:configuration:error:", "0x191f7c420"], "evidence": "per-op weight dumps from plan_devicesupport across N-conv chains (1/N for convs, 0 for relu); LLM-assisted decompile of the address-annotated factory listing; algebraic refutation of the additive model against the phase diagram", "caveat": "one machine/OS build; the factory read covered its own body plus the immediate same-image helper and did NOT follow the delegating callees; llvm-mc prints bl IMMEDIATES not addresses, so callee identification must use coreml_walk/coreml_findcallers instead", "contested": false}
```

---

## 4. Loading and executing a program, step by step

This is the Path A (MIL / in-memory) sequence as the code actually does it. Steps 1–5 are identical in
maderix/ANE, ANE-LM and libane; step 6 is where libane diverges with a faster dispatch.

| # | Step | Call |
|---|---|---|
| 0 | `dlopen` framework by path, look up the four classes | `dlopen`, `NSClassFromString` |
| 1 | Create descriptor from MIL text + weight blobs | `+modelWithMILText:weights:optionsPlist:` |
| 2 | Create model | `+inMemoryModelWithDescriptor:` |
| 3 | Get `hexStringIdentifier`; make `$TMPDIR/<hexID>/`, write `model.mil` and `weights/*` | filesystem |
| 4 | Compile (writes the compiled program into that directory) | `-compileWithQoS:options:error:` |
| 5 | Load into ANE | `-loadWithQoS:options:error:` |
| 6 | Create one `IOSurfaceRef` per input/output, wrap each in `_ANEIOSurfaceObject` | `IOSurfaceCreate`, `+objectWithIOSurface:` |
| 7 | Build the request once, keep it for the kernel's lifetime | `+requestWithInputs:inputIndices:outputs:outputIndices:weightsBuffer:perfStats:procedureIndex:` |
| 8 | Per inference: lock surface, `memcpy` input in, unlock | `IOSurfaceLock` / `IOSurfaceGetBaseAddress` |
| 9 | Evaluate | `-evaluateWithQoS:options:request:error:` (or the `processRequest:` fast path) |
| 10 | Per inference: lock output surface, `memcpy` out, unlock | IOSurface |
| 11 | Teardown: unload, release surfaces, remove temp dir | `-unloadWithQoS:error:` |

The complete loop, as written by maderix [MEASURED — maderix/ANE `bridge/ane_bridge.m`, survives
unmodified in a 7.2k-star repo with published benchmark numbers]:

```objc
// Source: maderix/ANE — bridge/ane_bridge.m (abridged to the call sequence)

// --- 1. descriptor -------------------------------------------------------
NSMutableDictionary *wdict = [NSMutableDictionary dictionary];
for (int i = 0; i < n_weights; i++) {
    NSString *name = [NSString stringWithUTF8String:weight_names[i]];   // "@model_path/weights/wq.bin"
    NSData   *data = [NSData dataWithBytes:weight_datas[i] length:weight_lens[i]];
    wdict[name] = @{@"offset": @0, @"data": data};
}
id desc = ((id(*)(Class,SEL,id,id,id))objc_msgSend)(
    g_ANEDesc, @selector(modelWithMILText:weights:optionsPlist:),
    milData, wdict.count > 0 ? wdict : @{}, nil);

// --- 2. model ------------------------------------------------------------
id mdl = ((id(*)(Class,SEL,id))objc_msgSend)(
    g_ANEInMem, @selector(inMemoryModelWithDescriptor:), desc);

// --- 3. temp dir keyed by hex id ----------------------------------------
id hx = ((id(*)(id,SEL))objc_msgSend)(mdl, @selector(hexStringIdentifier));
NSString *td = [NSTemporaryDirectory() stringByAppendingPathComponent:hx];
[fm createDirectoryAtPath:[td stringByAppendingPathComponent:@"weights"]
    withIntermediateDirectories:YES attributes:nil error:nil];
[milData writeToFile:[td stringByAppendingPathComponent:@"model.mil"] atomically:YES];
/* each weight written to td/<path with "@model_path/" stripped> */

// --- 4 & 5. compile, then load (QoS 21, options @{}) ---------------------
((BOOL(*)(id,SEL,unsigned int,id,NSError**))objc_msgSend)(
    mdl, @selector(compileWithQoS:options:error:), 21, @{}, &e);
BOOL loaded = ((BOOL(*)(id,SEL,unsigned int,id,NSError**))objc_msgSend)(
    mdl, @selector(loadWithQoS:options:error:), 21, @{}, &e);
if (!loaded) {                       // maderix retries once after 100 ms
    usleep(100000); e = nil;
    loaded = ((BOOL(*)(id,SEL,unsigned int,id,NSError**))objc_msgSend)(
        mdl, @selector(loadWithQoS:options:error:), 21, @{}, &e);
}

// --- 6. IOSurfaces are plain IOSurfaceCreate, not ANE objects ------------
static IOSurfaceRef create_surface(size_t bytes) {
    return IOSurfaceCreate((__bridge CFDictionaryRef)@{
        (id)kIOSurfaceWidth: @(bytes),        (id)kIOSurfaceHeight: @1,
        (id)kIOSurfaceBytesPerElement: @1,    (id)kIOSurfaceBytesPerRow: @(bytes),
        (id)kIOSurfaceAllocSize: @(bytes),    (id)kIOSurfacePixelFormat: @0
    });
}

// --- 7. request ----------------------------------------------------------
k->request = ((id(*)(Class,SEL,id,id,id,id,id,id,id))objc_msgSend)(
    g_ANEReq,
    @selector(requestWithInputs:inputIndices:outputs:outputIndices:weightsBuffer:perfStats:procedureIndex:),
    wIns, iIdx, wOuts, oIdx, nil, nil, @0);

// --- 8/9/10. per-inference ----------------------------------------------
IOSurfaceLock(kernel->ioInputs[idx], 0, NULL);
memcpy(IOSurfaceGetBaseAddress(kernel->ioInputs[idx]), data, bytes);
IOSurfaceUnlock(kernel->ioInputs[idx], 0, NULL);

((BOOL(*)(id,SEL,unsigned int,id,id,NSError**))objc_msgSend)(      // --- 9
    kernel->model, @selector(evaluateWithQoS:options:request:error:),
    21, @{}, kernel->request, &e);

IOSurfaceLock(kernel->ioOutputs[idx], kIOSurfaceLockReadOnly, NULL);
memcpy(data, IOSurfaceGetBaseAddress(kernel->ioOutputs[idx]), bytes);
IOSurfaceUnlock(kernel->ioOutputs[idx], kIOSurfaceLockReadOnly, NULL);

// --- 11. teardown --------------------------------------------------------
((BOOL(*)(id,SEL,unsigned int,NSError**))objc_msgSend)(
    kernel->model, @selector(unloadWithQoS:error:), 21, &e);
```

Two implementation details that are *not* obvious and that differ between projects:

* **Weight blob file naming.** maderix and ane-infer use the fixed name
  `@model_path/weights/weight.bin`; libane and ANE-LM key the dictionary (and the file on disk) by the
  *exact* `BLOBFILE(path=…)` string compiled into the MIL. The second is the safe form.
* **Program caching.** ANE-LM keeps a marker file in `~/Library/Caches/ane_lm/compiled_markers/<hexID>.ok`
  and, if present, skips `compileWithQoS:` and calls only `loadWithQoS:` [MEASURED — ANE-LM
  `core/ane_runtime.cpp`]. maderix instead retries `loadWithQoS:` once after 100 ms, which its author
  attributes to ANE slot reclamation [CLAIMED — code comment].

The weight blob layout is byte-identical in maderix's and ANE-LM's builders — good cross-validation of a
format nobody documented [MEASURED — both]:

```
offset 0   : 0x01
offset 4   : 0x02
offset 64  : EF BE AD DE        <- chunk magic
offset 68  : 0x01
offset 72  : uint32 weight_bytes (fp16 payload size)
offset 80  : uint32 128          <- payload offset
offset 128 : fp16 weights
```

### Fast dispatch (`processRequest:`), libane's Path A

libane calls the loaded program directly, bypassing `_ANEInMemoryModel`'s dispatch layer, and reports
0.365 ms/eval versus 0.413 ms for `evaluateWithQoS:` (≈13% lower latency) [MEASURED — libane
`docs/ane-runtime-boundary.md`]. The pieces it needs are reached entirely through KVC:

```objc
// Source: AmiraniLabs/libane — src/runtime/ane_runtime.mm
id inner     = [model valueForKey:@"model"];        // _ANEModel
id prog_eval = [inner valueForKey:@"program"];      // _ANEProgramForEvaluation
uint64_t string_id = ((uint64_t(*)(id,SEL))objc_msgSend)(inner, sel_registerName("string_id"));
/* …then processRequest:model:qos:qIndex:modelStringID:options:returnValue:error: as in §3.7 … */
```

---

## 5. The other path: `_ANEClient` + Espresso (Path B)

Path B is Core ML's own route: a compiled `.mlmodelc` directory is handed to `_ANEModel`, loaded through
`_ANEClient`, and the client's own surface mapper registers IOVAs. The full sequence, as libane implements
it [MEASURED — libane `ane_load_mlmodelc` + `ane_execute_client`]:

```objc
// Source: AmiraniLabs/libane — src/runtime/ane_runtime.mm
id client = ((id(*)(Class,SEL))objc_msgSend)(g_syms.cls_ANEClient, g_syms.sel_sharedConnection);

NSURL *dir_url = [NSURL fileURLWithPath:dir_ns];
id model_b = ((id(*)(Class,SEL,NSURL*,NSString*))objc_msgSend)(
    g_syms.cls_ANEModel_b, g_syms.sel_modelAtURLKey, dir_url, dir_ns);

((CompileFn)objc_msgSend)(client, g_syms.sel_compileModelOpts, model_b, @{}, kQoS, &error);
((LoadFn)objc_msgSend)(client, g_syms.sel_loadModel,        model_b, @{}, kQoS, &load_err);

// Read authoritative strides out of modelAttributes (KVC, no headers needed):
//   attrs[@"networkStatusList"][0][@"liveInputList"][0][@"batchStride" | @"planeStride"]
//   attrs[@"networkStatusList"][0][@"liveOutputList"][0][ ... ]

// Register surfaces with the firmware ONCE:
((MapFn)objc_msgSend)(client, g_syms.sel_mapIOSurfaces,
                      model_b, request, (BOOL)YES /*cacheInference*/, &map_err);

// Then every inference is:
((EvalDirectFn)objc_msgSend)(client, g_syms.sel_doEvalDirect,
                             model_b, @{}, request, kQoS, &error);

// Teardown:
((UnmapFn)objc_msgSend)(client, g_syms.sel_unmapIOSurfaces, model_b, request);
((UnloadFn)objc_msgSend)(client, g_syms.sel_doUnloadModel,  model_b, @{}, kQoS, nil);
```

Path B uses the 9-argument request initialiser with trailing `sharedEvents`/`transactionHandle` both
`nil`, because the 7-argument factory libane uses for Path A is what the model expects there
[MEASURED — libane]. Note also `_ANEIOSurfaceObject` constructed with an explicit offset and
`shouldRetain:YES` on this path.

The key structural difference, which libane documents as the explanation for several blocked features:
**only Path B allocates a non-zero `intermediateBufferHandle`**, and the firmware gates chaining,
IOSurface pre-mapping, `startOffset`, and shared events on that handle
[MEASURED — libane, with a per-feature table]. In libane's words, Path A's
`intermediateBufferHandle` is "always 0 (never allocated)"; `queueDepth` is 127.

The shared-events half of that gating is now corroborated two further ways, independent of libane:
our own deterministic SIGSEGV at `processRequest+1524` (addr 0x10) when a populated `_ANESharedEvents`
is attached on Path A, and the `tmc/apple` Go guard `ErrSharedEventRequiresPackage` ("shared events
require package-backed models (ModelTypePackage)"; in-memory MIL returns that error where the raw
framework crashes) — §3.12, `results/EXP-025-ane-gpu-sync/` [MEASURED 2026-10-07 M5 Max / 27.0.1 +
DOCUMENTED — pkg.go.dev/github.com/tmc/apple/x/ane]. The positive Path-B test is EXP-025's declared
GAP (Lane A).

**2026-10-07 phase-2 correction — the espresso door is legacy.** The claimed blocker for that positive
test ("no Xcode toolchain") was wrong: public `+[MLModel compileModelAtURL:error:]` compiles an
`.mlpackage` CLT-only in <1 s on 27.0.1, emitting `{analytics/, coremldata.bin, model.mil,
weights/weight.bin}` — and **no current bundle format contains `model.espresso.net` at all**, old EXP-003-era
bundle or freshly compiled (`EXP-025 results/p2_bundle_diff.txt`). Feeding such a bundle through the
sequence above fails identically at both doors (`compileModel:` and `loadModel:`):
`_ANEEspressoIRTranslator : error Cannot load network '<bundle>/model.espresso.net'`
(`EXP-025 results/p2_espresso_net_wall.txt`). Root `fs_usage` shows where 27 actually compiles:
`ANECompilerService.xpc` writes `model.src` and produces `model.hwx` in a hash-keyed cache that `aned`
reads back — the live pipeline is MIL → ANECompilerService → `model.hwx` → aned, and the espresso-net
demand belongs to a file generation only the in-process Core ML engine stack produces
(`EXP-025 docs/P2-LANE-A.md` §1–3, `results/p2_compile_at_url.txt`). Related first routing measurement:
over a 600-predict public loop `enginemon` recorded GPU Energy 2.35 J with ANE 0.0 mW / 0 handlers /
0 B DCS on a model whose ANE material was compiled — E5's router chose GPU invisibly to `MLComputePlan`
(`EXP-025 results/p2_enginemon_gpu.txt`).

**Kitchen inventory (phase-2B, 2026-10-07, Mac17,14 / 27.0.1, all MEASURED — `results/EXP-026-ane-kitchen/`):**
`ANECompiler.framework` dlopens on 27 and exports 140 `_ANEC*` symbols — `ANECCompile`,
`ANECCompileJIT/Offline/Online/WithFunctionCall`, per-layer `ANECConvLayerDescInitialize`-style
netlist descriptors, `ANECGetMPSDialectSupportedVersion` — but the legacy C door refuses every
coremltools-9 / coremlc-3600 `model.mil` with `ErrorList=(InvalidMILProgram)`: 7/7 synthetic conv
chains plus the real MiniLM bundle, identical across `h13g/h16g/h17c` targets (dialect-level refusal,
not op support; renaming the input to `model.src` shifts the error to `InvalidCompilationParam`).
The modern MIL front-end is **`MilAneflow.framework`**, a small C API — `make_milaneflow_context`,
`milaneflow_try_program_from_string` / `_from_file`, `try_function` (op-support oracle),
`execute_function`, `opset_name_list` + error-copy pair — absent from every published map
(freedomtan, tinygrad/geohot, Bryngelson); its ABI resisted probing this session (valid and
garbage MIL both return status 0 with a NULL program via all tried signatures). Neither compiler
XPC service has `MachServices` in its Info.plist and neither is registered in the launchd system
domain (`launchctl print` → *Bad request*; `NSXPCConnection` lookup → error 3); direct-exec of the
service binary runs as user but exits rc=1 under root — it is spawned on demand by the CoreML
client stack, not by launchd. The public loader's identity bookkeeping lives in
`~/Library/Caches/<clientproc>/com.apple.e5rt.e5bundlecache/<OSBUILD>/<IDENT64>/model.milhash`
(re-readable!): `<IDENT64>` re-keys when weight bytes or MIL text change. The follow-up proof test
(EXP-027) then **refuted the stale-program consequence** on the public path: an in-place weight-byte
edit at the cache-warmed bundle path changed the prediction vector exactly as the same edit did at a
cold path (output FNV `584eafc1…` → `56a76798…`; load re-planned 143.7 ms vs 30.5 ms cached) —
**FRESH verdict**, hazard downgraded to bookkeeping-only for GPU-routed public loads (full-ANE-AOT
bundles untested; residual). Note also that `.mlmodelc` `weights/weight.bin` opens with a ~1 KiB
manifest (0xDEADBEEF magic, tensor count/sizes); overwriting its head fails the load hard
(*execution plan … error code: -5*), so whole-file weight pokes must respect the data boundary
[API-123]. Finally, espresso is not dead input, only a dead package-format: compiling a
legacy `.mlmodel` (not `.mlpackage`) through the same public `compileModelAtURL:` on 27.0.1 emits a
full espresso trio (`model.espresso.net/.shape/.weights`), and the `EXP-025` `pkgb` harness then
fails two stages *deeper* on that bundle — `mapIOSurfacesWithModel:` 0x1D (surface geometry) —
instead of at the translator [API-117…API-123].

---

## 6. Reaching the framework from other languages

Almost nobody writes ObjC app code against this API. The dominant pattern is: a small ObjC/C shim exposes
plain C functions, and the real program lives in Python/Rust/Go/Swift. Two variants exist.

### 6.1 Dynamic ObjC from C/C++ without headers (`objc_msgSend` + `sel_registerName`)

This is what ANE-LM does: compile the runtime as Objective-C++ and call everything through
`objc_msgSend` with hand-written casts. It links no private headers at all.

```cpp
// Source: johnmai-dev/ANE-LM — core/ane_runtime.cpp
static inline SEL sel(const char* n) { return sel_registerName(n); }

id desc = ((id(*)(Class,SEL,id,id,id))objc_msgSend)(
    g_ANEDesc, sel("modelWithMILText:weights:optionsPlist:"),
    milText, wdict ? wdict : ns_empty_dict(), (id)nullptr);

id mdl = ((id(*)(Class,SEL,id))objc_msgSend)(
    g_ANEInMem, sel("inMemoryModelWithDescriptor:"), desc);

bool ok = ((bool(*)(id,SEL,unsigned int,id,id*))objc_msgSend)(
    mdl, sel("evaluateWithQoS:options:request:error:"), 21, ns_empty_dict(), k->request, &e);
```

The cost is that the cast encodes the argument types: get one wrong and you get silent corruption, not a
compile error. This is the single biggest source of risk when re-implementing the API.

### 6.2 Python `ctypes` into a shim dylib

maderix's `bridge/` and ane-infer's `ane-bridge` both compile an ObjC `.dylib` and expose C functions:

```c
// Source: maderix/ANE — bridge/ane_bridge.h
int              ane_bridge_init(void);
ANEKernelHandle *ane_bridge_compile(const char *mil_text, size_t mil_len,
                                    const uint8_t *weight_data, size_t weight_len,
                                    int n_inputs, const size_t *input_sizes,
                                    int n_outputs, const size_t *output_sizes);
bool ane_bridge_eval(ANEKernelHandle *kernel);
void ane_bridge_write_input(ANEKernelHandle *kernel, int idx, const void *data, size_t bytes);
void ane_bridge_read_output(ANEKernelHandle *kernel, int idx, void *data, size_t bytes);
void ane_bridge_free(ANEKernelHandle *kernel);
uint8_t *ane_bridge_build_weight_blob(const float *src, int rows, int cols, size_t *out_len);
```

Python then just declares argtypes and calls it; the ANE-specific knowledge stays in ObjC where
`@selector` strings can be checked at compile time.

### 6.3 Rust

ane-infer links the ObjC shim at build time and declares the C functions as `extern "C"`:

```rust
// Source: thebasedcapital/ane-infer — crates/ane-bridge/build.rs
cc::Build::new()
    .file("objc/ane_runtime.m")
    .flag("-fno-objc-arc")   // manual retain/release; ARC cannot handle `id` fields in C structs
    .flag("-fmodules")
    .compile("ane_runtime");
// + link Foundation, IOSurface, libobjc

// Source: crates/ane-bridge/src/lib.rs
unsafe extern "C" {
    pub fn ane_init() -> i32;
    pub fn ane_eval(k: *mut ANEKernel) -> bool;
    pub fn ane_eval_procedure(k: *mut ANEKernel, proc_idx: i32) -> bool;
    …
}
```

The `-fno-objc-arc` flag is a real finding: these APIs force you into manual retain/release because the
handles live in C structs that ARC will not manage.

### 6.4 Go

`github.com/tmc/apple/private/appleneuralengine` binds the whole framework with `purego` (cgo-free),
calling `objc.Send[bool](id, objc.Sel("compileWithQoS:options:error:"), qos, options, unsafe.Pointer(&err))`.
It is auto-generated, which means it is a *complete* inventory of the class/method surface — and it is the
single most useful source in this file for that reason. It is also unverified: I found no report of anyone
running the Go bindings against the ANE.

### 6.5 The layer below: direct H11ANE IOKit (not this API)

geohot's tinygrad ANE work predates the in-memory-model API and talks to the `H11ANE` kernel driver
directly, assembling raw program-request structs. Example [MEASURED — tinygrad
`extra/accel/ane/lib/ane.mm`]:

```objc
H11ANEDeviceController dc(MyH11ANEDeviceControllerNotification, NULL);
dc.SetupDeviceController();
dev->H11ANEDeviceOpen(MyH11ANEDeviceMessageNotification, empty, UsageCompile, &dis);
dev->ANE_ProgramCreate(&mprog, out);      // -> program_handle
dev->ANE_ProgramPrepare(&pas);
dev->ANE_ProgramSendRequest(pras, recvPort);
```

Its documented caveat is that disabling AMFI was required for this path, and that direct hwx execution
needs a connection to `aned`, i.e. **the framework is the practical entry point, not IOKit**
[MEASURED — tinygrad `extra/accel/ane/README.md`].

---

## 7. Where sources disagree

| # | Question | Position A | Position B | Status |
|---|---|---|---|---|
| 1 | Are weights patchable after compile? | **Yes.** Unload, overwrite `weights/*.bin` on disk, reload — 4,200 ms → 494 ms per step (Orion, arXiv 2603.06728) | **No.** "Writing new weight blobs to disk before `loadWithQoS:` has zero effect on execution. Weight values cannot be changed without a full recompile." (libane, `probe_delta_reload`, 2026-04-16) | **Contested, unresolved.** Both are specific measurements. maderix ships `test_weight_patch.m`/`test_weight_reload.m` that probe exactly this (disk patch + unload/reload, then a memory scan for the compiled weight bytes) but the repo states no verdict; maderix's production pipeline instead packs weights into the spatial dimension as *inputs* to avoid recompiling, which suggests it did not rely on disk patching. |
| 2 | Is `doEvaluateDirectWithModel:` faster? | **Yes, ~10%** — 106 µs vs 117 µs (ane-infer) | **No, 18% slower** — 401 µs vs 346 µs for `processRequest:` on Path A (libane, 2026-04-17) | **Contested, probably not actually conflicting.** libane explicitly argues ane-infer's comparison baseline was Core ML's `evaluateWithModel:`, not `processRequest:`, so the two numbers measure different baselines. Treat "the `do`-prefixed and `processRequest:` paths skip the daemon XPC hop" as the reliable part. |
| 3 | Multi-input programs | **Work.** libane and ane-infer both build multi-input requests; Orion documents exactly how (equal alloc sizes, alphabetical order) | **Fail.** maderix and our own sweep report a single-input constraint, so maderix packs inputs into one surface's spatial dimension | **Contested.** Most likely a per-program/per-MIL-version issue, not a hardware law. Not resolved by anything I read. |
| 4 | `doEvaluateDirectWithModel:` arity | 4 args: `…WithModel:request:qos:error:` (iOS-era header) | 5 args: `…WithModel:options:request:qos:error:` (every modern project + current dump) | **Not a dispute — a version difference.** Both are attested. |
| 5 | Is `_ANECompiler` a class? | Named as a class by Orion's Table 2 and loosely by maderix's README | Absent from every class dump and from all working code, which compiles via `_ANEInMemoryModel` | **Contested naming.** The compile *step* exists; a class by that name is not evidenced. |
| 6 | What is QoS `21`? | Hardcoded by every project | `_ANEQoSMapper.aneDefaultTaskQoS` exists and is the obvious candidate | **Unresolved** (my `21 == aneDefaultTaskQoS` reading is INFERRED; nobody has printed both). |

---

## 8. What is NOT known

This is the most important section. Nothing below should be treated as implementable without
verification on the target machine.

1. **Argument types are reconstructed, not authoritative.** Only the *selector strings* are attested for
   most calls (§3 marks these `(call-site)`). The real encodings come from casts written by reverse
   engineers. Anyone re-implementing should treat every cast as a hypothesis.
2. **`_ANEInMemoryModel`'s exact ivar layout is third-party.** ane-infer's offset table
   (`[+8] _queueDepth = 127`, `[+32] _intermediateBufferHandle`, `[+64] _ANEModel`, `[+96] _state = 3`,
   …) is a single source, unpublished elsewhere, and I could not cross-check it except that the field
   *names* match the current method dump. Offsets are doubly fragile: they change per OS build.
3. **`intermediateBufferHandle`'s semantics.** Everyone agrees non-zero implies firmware-side buffer
   registration, but whether a non-zero value *means* "spilled to DRAM" (ane-infer) or simply "registered
   through `_ANEClient`" (libane) is unresolved. Those are different claims and both are asserted.
4. **Perf stats.** `_ANEPerformanceStats` / `_ANEPerformanceStatsIOSurface` exist, and the request has
   `perfStats`/`perfStatsMask` slots, but I found **no published decode** of a stats buffer: not the field
   layout, not the units, not the meaning of `perfStatsMask` bits. tinygrad's captured `perfStatsMask=0`
   is the only concrete value I saw.
5. **`queueDepth` (127).** Observed, never explained. It is plausibly the ANE's max in-flight evaluations,
   but nothing states that.
6. **`state`'s enum.** Values `1` (unloaded, from a live capture) and `3` (loaded, from ane-infer) are the
   only two observed; the rest of the enum is unknown.
7. **The whole chaining state machine.** `prepareChainingWithModel:` succeeding while
   `buffersReadyWithModel:` fails silently is the state of the art. Which inputs make chaining actually
   run, what `fwEnqueueDelay`, `memoryPoolId` and `transactionHandle` do, and whether `lbInputSymbolId` /
   `lbOutputSymbolId` are symbol indices or addresses — all unknown.
8. **`_ANESharedEvents` on the MIL path — narrowed, not closed.** libane's `EXC_BAD_ACCESS` at
   `address 0x10` inside `-[_ANEProgramForEvaluation processRequest:...]_block_invoke` was
   reproduced here, deterministically, at `+1524` on M5 Max / macOS 27.0.1, and the package-only
   gating is now a guarded (not merely crashed) behaviour in `tmc/apple` Go
   (`ErrSharedEventRequiresPackage`). Still unknown: the firmware wait-loop internals, the roles of
   `symbolIndex`/`eventType`/`agentMask`, whether a non-nil `intermediateBufferHandle` on Path A
   avoids the crash, and the end-to-end Path-B event timing (§3.12; EXP-025 Lane A).
   Phase-2 status (2026-10-07): the `_ANEClient` route to that timing is a dead end on 27
   (espresso-net demand, §5 correction); the re-scoped route is driving `ANECompilerService.xpc`
   or riding the E5 path — whose steady-state dtrace census shows it already wires predictions
   through mach-port shared events (`newSharedEventWithMachPort:` ×131/predict window) and
   IO-fence toggling (`EXP-025 results/p2_census_e5_selectors.txt`). The `tmc` option keys
   `kANEFDisableIOFencesUseSharedEventsKey` and `kANEFEnableFWToFWSignal` are confirmed present
   in-process on 27.0.1 by dlopen string scan, with a block encoding typed directly on
   `IOSurfaceSharedEvent` (`v24@?0@"IOSurfaceSharedEvent"8Q16`); behavior probes still pending
   on a loaded program (`EXP-025 results/p2_kanef_strings.txt`).
9. **`_ANEVirtualClient`, `_ANEModelToken`, `_ANEProcedureData`, `_ANEWeight`,
   `_ANEModelInstanceParameters`.** Present in the dump, essentially unexamined publicly. maderix's
   `test_weight_patch.m` tries `weightWithSymbolAndURL:weightURL:` and reads `weightSymbol`/`weightURL`,
   then attempts to pass the result as a request's `weightsBuffer:` — the outcome is not recorded in the
   source I read.
10. **Most `_ANEModel` initializers.** The 13-argument `modelAtURLWithSourceURL:sourceURL:uuid:key:
    identifierSource:cacheURLIdentifier:modelAttributes:standardizeURL:string_id:generateNewStringId:
    mpsConstants:` family is decoded only as far as argument names; `identifierSource`'s integer values
    and `generateNewStringId`'s effect are unknown.
11. **Whether any of this survives an OS update.** The class dump and every project agree these are
    private; there is no ABI promise. The iOS dump in `nst/iOS-Runtime-Headers` and the current macOS dump
    already differ in class set *and* method signatures, which is a concrete demonstration of drift.
12. **Anything about the compiler's internals.** `ANECCompile()`, its flag dictionary
    (`TargetArchitecture`, `CompileANEProgramForDebugging`, `DebugMask`), and the `net.plist` input format
    are known from tinygrad's exploration and from log strings — but the documented API is opaque and the
    only supported way in is "hand it MIL and see". No project I read documents an error taxonomy beyond a
    handful of numeric codes (`0x2`, `0x12`/13, `0x1d`, `15`).

---

## Sources

Local paths (this machine):

* `/System/Library/PrivateFrameworks/AppleNeuralEngine.framework/` — bundle and its three `.xpc` services (directory listing, MEASURED)
* `/Volumes/data/local_ai_stack/repos/neural-engine/docs/is-model-using-ane.md` — breakpoint technique `-[_ANEModel program]`
* `/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/coreai-error-index.md` (line 524-530) — `_ANECompiler : ANECCompile() FAILED` error text
* `/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/compression-reference.md` (line 115) — noting that string is usually noise
* `/Volumes/data/local_ai_stack/results/RESEARCH-SWEEP.md` — our own sweep, incl. the stated single-input constraint
* `results/EXP-025-ane-gpu-sync/` — our own shared-event evidence pack (VERDICT, class dumps, porttest, dtrace census, lldb instance proof, harness sources; transferred from `AI_dev` 2026-10-07; phase-2 additions `docs/P2-LANE-A.md` + `results/p2_*.txt` 2026-10-07) (MEASURED)

External, fetched and read on 2026-09-23:

* https://github.com/nst/iOS-Runtime-Headers/tree/master/PrivateFrameworks/AppleNeuralEngine.framework — `_ANEClient.h`, `_ANEModel.h`, `_ANERequest.h`, `_ANEDaemonConnection.h`, `_ANEIOSurfaceObject.h`, `_ANEProgramForEvaluation.h`, `_ANEDeviceController.h`, `_ANEDeviceInfo.h`, `_ANEStrings.h`, `_ANEErrors.h`, `_ANEQoSMapper.h`, `_ANECloneHelper.h`, `_ANEHashEncoding.h`, `_ANELog.h`, `_ANEDataReporter.h` (old iOS era; repo archived read-only 2026-09-08)
* https://github.com/maderix/ANE — `bridge/ane_bridge.m`, `bridge/ane_bridge.h`, `bridge/Makefile`, `api_exploration.m`, `training/ane_runtime.h`, `training/test_weight_patch.m`, `training/test_weight_reload.m`, `README.md`
* https://github.com/johnmai-dev/ANE-LM — `core/ane_runtime.cpp`, `core/ane_runtime.h`
* https://github.com/AmiraniLabs/libane — `src/runtime/ane_runtime.mm`, `docs/ane-runtime-boundary.md`, `README.md`, `include/libane.h`, `bindings/python/ane.pyi`
* https://github.com/thebasedcapital/ane-infer — `crates/ane-bridge/objc/ane_runtime.m`, `crates/ane-bridge/build.rs`, `crates/ane-bridge/src/lib.rs`, `docs/ane-internals.md`
* https://github.com/tinygrad/tinygrad/tree/d0e752003da3fc023fa85094d7f5b65b47dd5091/extra/accel/ane — `README.md`, `lib/ane.mm`, `lib/ane.py`, `3_run/entitlements.xml`
* https://github.com/tmc/apple/tree/main/private/appleneuralengine — generated bindings, one `*_name_.gen.go` per class (current-macOS class and method inventory)
* https://arxiv.org/abs/2603.06728 — "Orion: Characterizing and Programming Apple's Neural Engine for LLM Training and Inference" (private-API table, delta compilation, 20-constraint catalog)

External, fetched and read on 2026-10-07 (ane-sync session):

* https://pkg.go.dev/github.com/tmc/apple/x/ane — Go binding guard `ErrSharedEventRequiresPackage` ("shared events require package-backed models (ModelTypePackage)"), `SharedEventEvalOptions` naming `kANEFDisableIOFencesUseSharedEventsKey` and `kANEFEnableFWToFWSignal`, and the `SharedEventFromPort`/`EvalWithSignalEvent` port API that independently confirms the mach-port bridge in §3.12

---

## Records

```jsonl
{"id":"API-001","claim":"AppleNeuralEngine.framework lives at /System/Library/PrivateFrameworks/AppleNeuralEngine.framework/ and its dylib is not present as a file on macOS 27 because the binary is in the dyld shared cache.","kind":"fact","confidence":"measured","source":"/System/Library/PrivateFrameworks/AppleNeuralEngine.framework/","source_type":"our-own","retrieved":"2026-09-23","topic":["api","packaging"],"entities":["AppleNeuralEngine.framework","macOS 27"],"evidence":"AppleNeuralEngine is a symlink to Versions/Current/AppleNeuralEngine, whose target does not exist on disk","caveat":"observed on this Mac mini M4 only","contested":false}
{"id":"API-002","claim":"AppleNeuralEngine.framework ships three XPC services: ANECompilerService.xpc, ANELargeModelCompilerService.xpc and ANEStorageMaintainer.xpc.","kind":"fact","confidence":"measured","source":"/System/Library/PrivateFrameworks/AppleNeuralEngine.framework/XPCServices","source_type":"our-own","retrieved":"2026-09-23","topic":["api","architecture"],"entities":["ANECompilerService.xpc","ANELargeModelCompilerService.xpc","ANEStorageMaintainer.xpc"],"contested":false,"split":"holdout"}
{"id":"API-003","claim":"A program reaches the private ANE API by dlopen-ing the framework path and looking up classes with NSClassFromString, with no entitlement required on macOS.","kind":"procedure","confidence":"measured","source":"https://github.com/maderix/ANE/blob/main/bridge/ane_bridge.m","source_type":"primary","retrieved":"2026-09-23","topic":["api","loading"],"entities":["_ANEInMemoryModel","maderix/ANE"],"evidence":"bridge/Makefile builds an unsigned dylib with clang -fobjc-arc -dynamiclib -framework Foundation -framework IOSurface -ldl","contested":false}
{"id":"API-004","claim":"The entitlement com.apple.ane.iokit-user-access is required for the direct H11ANE IOKit path, not for the AppleNeuralEngine framework path.","kind":"fact","confidence":"documented","source":"https://github.com/tinygrad/tinygrad/blob/d0e752003da3fc023fa85094d7f5b65b47dd5091/extra/accel/ane/3_run/entitlements.xml","source_type":"primary","retrieved":"2026-09-23","topic":["api","entitlements"],"entities":["com.apple.ane.iokit-user-access","H11ANE","tinygrad"],"contested":false}
{"id":"API-005","claim":"The class _ANEInMemoryModelDescriptor describes a model to be compiled, holding MIL program text, weight blobs and an options plist.","kind":"definition","confidence":"documented","source":"https://github.com/tmc/apple/blob/main/private/appleneuralengine/ane_in_memory_model_descriptor.gen.go","source_type":"secondary","retrieved":"2026-09-23","topic":["api","classes"],"entities":["_ANEInMemoryModelDescriptor"],"contested":false}
{"id":"API-006","claim":"The factory selector +modelWithMILText:weights:optionsPlist: creates an _ANEInMemoryModelDescriptor and its MIL text argument must be an NSData of UTF-8 bytes rather than an NSString.","kind":"gotcha","confidence":"measured","source":"https://github.com/thebasedcapital/ane-infer/blob/main/docs/ane-internals.md","source_type":"primary","retrieved":"2026-09-23","topic":["api","gotchas"],"entities":["_ANEInMemoryModelDescriptor","modelWithMILText:weights:optionsPlist:"],"evidence":"Orion constraint #9: 'MIL text must be NSData*, not NSString* — immediate crash'","contested":false}
{"id":"API-007","claim":"The weights argument to +modelWithMILText:weights:optionsPlist: must be an empty NSDictionary @{} and never nil when the program has no weights.","kind":"gotcha","confidence":"documented","source":"https://github.com/AmiraniLabs/libane/blob/main/src/runtime/ane_runtime.mm","source_type":"primary","retrieved":"2026-09-23","topic":["api","gotchas"],"entities":["_ANEInMemoryModelDescriptor","libane"],"evidence":"comment: 'CRITICAL: must be @{} (empty dict), never nil, for weight-free programs'","contested":false}
{"id":"API-008","claim":"Weight dictionary keys in an _ANEInMemoryModelDescriptor are the exact BLOBFILE path strings written in the MIL program, such as @model_path/weights/weight.bin, each mapping to a dictionary with offset and data entries.","kind":"procedure","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/src/runtime/ane_runtime.mm","source_type":"primary","retrieved":"2026-09-23","topic":["api","program-format"],"entities":["BLOBFILE","_ANEInMemoryModelDescriptor"],"contested":false}
{"id":"API-009","claim":"The class _ANEInMemoryModel wraps a descriptor and owns the compile, load, evaluate and unload lifecycle plus the temporary directory the compiler writes into.","kind":"definition","confidence":"documented","source":"https://github.com/tmc/apple/blob/main/private/appleneuralengine/ane_in_memory_model.gen.go","source_type":"secondary","retrieved":"2026-09-23","topic":["api","classes"],"entities":["_ANEInMemoryModel"],"contested":false}
{"id":"API-010","claim":"+inMemoryModelWithDescriptor: is the entry point that turns an _ANEInMemoryModelDescriptor into an _ANEInMemoryModel.","kind":"procedure","confidence":"measured","source":"https://github.com/maderix/ANE/blob/main/bridge/ane_bridge.m","source_type":"primary","retrieved":"2026-09-23","topic":["api"],"entities":["_ANEInMemoryModel","inMemoryModelWithDescriptor:"],"contested":false}
{"id":"API-011","claim":"_ANEInMemoryModel exposes the lifecycle selectors compileWithQoS:options:error:, loadWithQoS:options:error:, evaluateWithQoS:options:request:error: and unloadWithQoS:error:.","kind":"fact","confidence":"measured","source":"https://github.com/maderix/ANE/blob/main/bridge/ane_bridge.m","source_type":"primary","retrieved":"2026-09-23","topic":["api","signatures"],"entities":["_ANEInMemoryModel"],"contested":false,"split":"holdout"}
{"id":"API-012","claim":"Every public call site passes QoS value 21 to the _ANEInMemoryModel lifecycle methods and passes @{} rather than nil for the options argument.","kind":"procedure","confidence":"measured","source":"https://github.com/johnmai-dev/ANE-LM/blob/main/core/ane_runtime.cpp","source_type":"primary","retrieved":"2026-09-23","topic":["api","signatures"],"entities":["_ANEInMemoryModel","QoS"],"evidence":"libane defines static constexpr unsigned int kQoS = 21 and calls compileWithQoS:kQoS options:@{} error:&error","contested":false}
{"id":"API-013","claim":"The meaning of the hardcoded QoS value 21 is not proven, but the framework class _ANEQoSMapper exposes +aneDefaultTaskQoS which is the obvious candidate.","kind":"open-question","confidence":"inferred","source":"https://github.com/tmc/apple/blob/main/private/appleneuralengine/ane_qo_s_mapper.gen.go","source_type":"secondary","retrieved":"2026-09-23","topic":["api","open-questions"],"entities":["_ANEQoSMapper","QoS"],"caveat":"no public source prints both values","contested":false}
{"id":"API-014","claim":"-hexStringIdentifier on _ANEInMemoryModel returns a stable identifier that projects use as the temp directory name for model.mil and weights files.","kind":"procedure","confidence":"measured","source":"https://github.com/maderix/ANE/blob/main/bridge/ane_bridge.m","source_type":"primary","retrieved":"2026-09-23","topic":["api","procedure"],"entities":["_ANEInMemoryModel","hexStringIdentifier"],"contested":false}
{"id":"API-015","claim":"The compiler requires the MIL text and weight files to exist on disk under the model's hex-string temp directory before compileWithQoS: is called.","kind":"gotcha","confidence":"measured","source":"https://github.com/johnmai-dev/ANE-LM/blob/main/core/ane_runtime.cpp","source_type":"primary","retrieved":"2026-09-23","topic":["api","compilation"],"entities":["_ANEInMemoryModel","model.mil"],"contested":false}
{"id":"API-016","claim":"_ANEInMemoryModel exposes an intermediateBufferHandle property that libane reads after load as an SRAM-spill signal.","kind":"fact","confidence":"documented","source":"https://github.com/tmc/apple/blob/main/private/appleneuralengine/ane_in_memory_model.gen.go","source_type":"secondary","retrieved":"2026-09-23","topic":["api","memory"],"entities":["_ANEInMemoryModel","intermediateBufferHandle"],"contested":false}
{"id":"API-017","claim":"libane reports that intermediateBufferHandle is always zero on the MIL/in-memory path and that the firmware allocates it only when a model is loaded through _ANEClient.","kind":"measurement","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/docs/ane-runtime-boundary.md","source_type":"primary","retrieved":"2026-09-23","topic":["api","memory","residency"],"entities":["intermediateBufferHandle","_ANEClient","libane"],"caveat":"reported by one project; the ivar may differ per OS build","contested":false}
{"id":"API-018","claim":"ane-infer asserts that a non-zero intermediateBufferHandle means the model's intermediate activations exceeded roughly 32 MB of on-chip SRAM and were spilled to DRAM.","kind":"open-question","confidence":"claimed","source":"https://github.com/AmiraniLabs/libane/blob/main/src/runtime/ane_runtime.mm","source_type":"secondary","retrieved":"2026-09-23","topic":["api","memory"],"entities":["intermediateBufferHandle","SRAM"],"evidence":"libane's runtime prints 'SRAM spill detected (intermediateBufferHandle=%llu) — model exceeds ~32 MB SRAM'","caveat":"this interpretation appears in libane's own warning text and is not independently verified","contested":false}
{"id":"API-019","claim":"_ANEInMemoryModel exposes a model property returning the underlying _ANEModel kernel handle.","kind":"fact","confidence":"documented","source":"https://github.com/tmc/apple/blob/main/private/appleneuralengine/ane_in_memory_model.gen.go","source_type":"secondary","retrieved":"2026-09-23","topic":["api","classes"],"entities":["_ANEInMemoryModel","_ANEModel"],"contested":false}
{"id":"API-020","claim":"_ANEModel is the kernel-side handle for a loaded program, carrying programHandle, string_id, uuid, modelAttributes and an IOSurface mapper.","kind":"definition","confidence":"documented","source":"https://github.com/tmc/apple/blob/main/private/appleneuralengine/ane_model.gen.go","source_type":"secondary","retrieved":"2026-09-23","topic":["api","classes"],"entities":["_ANEModel"],"contested":false}
{"id":"API-021","claim":"+modelAtURL:key: is the _ANEModel factory that libane uses to load a compiled .mlmodelc directory through _ANEClient.","kind":"procedure","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/src/runtime/ane_runtime.mm","source_type":"primary","retrieved":"2026-09-23","topic":["api","procedure"],"entities":["_ANEModel","modelAtURL:key:","libane"],"contested":false}
{"id":"API-022","claim":"_ANEModel.string_id is read via KVC and passed as the modelStringID argument of _ANEProgramForEvaluation processRequest:.","kind":"procedure","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/src/runtime/ane_runtime.mm","source_type":"primary","retrieved":"2026-09-23","topic":["api","procedure"],"entities":["_ANEModel","string_id","processRequest:"],"contested":false,"split":"holdout"}
{"id":"API-023","claim":"_ANEInMemoryModel exposes an initWithDesctiptor: initialiser whose selector contains Apple's spelling typo Desctiptor.","kind":"gotcha","confidence":"documented","source":"https://github.com/tmc/apple/blob/main/private/appleneuralengine/ane_in_memory_model.gen.go","source_type":"secondary","retrieved":"2026-09-23","topic":["api","gotchas"],"entities":["_ANEInMemoryModel","initWithDesctiptor:"],"contested":false}
{"id":"API-024","claim":"The class _ANERequest describes one evaluation: input surfaces, input indices, output surfaces, output indices, weights buffer, perf stats and procedure index.","kind":"definition","confidence":"documented","source":"https://github.com/tmc/apple/blob/main/private/appleneuralengine/ane_request.gen.go","source_type":"secondary","retrieved":"2026-09-23","topic":["api","classes"],"entities":["_ANERequest"],"contested":false}
{"id":"API-025","claim":"The 7-argument factory +requestWithInputs:inputIndices:outputs:outputIndices:weightsBuffer:perfStats:procedureIndex: is the request constructor used by every public project.","kind":"procedure","confidence":"measured","source":"https://github.com/maderix/ANE/blob/main/bridge/ane_bridge.m","source_type":"primary","retrieved":"2026-09-23","topic":["api","signatures"],"entities":["_ANERequest"],"evidence":"identical call in maderix/ANE, ANE-LM, libane and ane-infer","contested":false}
{"id":"API-026","claim":"Public projects pass nil for both the weightsBuffer and perfStats arguments of the request factory and build one request object per kernel for reuse across evaluations.","kind":"procedure","confidence":"measured","source":"https://github.com/maderix/ANE/blob/main/bridge/ane_bridge.m","source_type":"primary","retrieved":"2026-09-23","topic":["api","procedure"],"entities":["_ANERequest"],"contested":false}
{"id":"API-027","claim":"_ANERequest has a completionHandler block property that fires asynchronously after evaluateWithQoS: returns, with the IOSurface output already coherent.","kind":"fact","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/docs/ane-runtime-boundary.md","source_type":"primary","retrieved":"2026-09-23","topic":["api","async"],"entities":["_ANERequest","completionHandler","ANEServicesThread"],"evidence":"handler fires ~0.2 ms after eval wall time of 0.1-0.4 ms","contested":false}
{"id":"API-028","claim":"The class _ANEIOSurfaceObject wraps a raw IOSurfaceRef so that it can be placed in an _ANERequest.","kind":"definition","confidence":"measured","source":"https://github.com/maderix/ANE/blob/main/bridge/ane_bridge.m","source_type":"primary","retrieved":"2026-09-23","topic":["api","classes"],"entities":["_ANEIOSurfaceObject"],"contested":false}
{"id":"API-029","claim":"+objectWithIOSurface: is the _ANEIOSurfaceObject factory used by maderix/ANE, ANE-LM and ane-infer.","kind":"procedure","confidence":"measured","source":"https://github.com/maderix/ANE/blob/main/bridge/ane_bridge.m","source_type":"primary","retrieved":"2026-09-23","topic":["api","signatures"],"entities":["_ANEIOSurfaceObject","objectWithIOSurface:"],"contested":false}
{"id":"API-030","claim":"_ANEIOSurfaceObject also offers initWithIOSurface:startOffset:shouldRetain: and objectWithIOSurface:startOffset:, which libane uses on the Path B _ANEClient route.","kind":"fact","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/src/runtime/ane_runtime.mm","source_type":"primary","retrieved":"2026-09-23","topic":["api","signatures"],"entities":["_ANEIOSurfaceObject","startOffset"],"contested":false}
{"id":"API-031","claim":"On the MIL/in-memory path the ANE DMA ignores _ANEIOSurfaceObject startOffset and always reads and writes from the surface base address.","kind":"gotcha","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/docs/ane-runtime-boundary.md","source_type":"primary","retrieved":"2026-09-23","topic":["api","memory","gotchas"],"entities":["startOffset","libane"],"evidence":"offsets 1, 64, 128, 256, 512, 1K, 4K, 8K, 16K all produced output at byte 0 with sum(|data at slotT|) = 0.00","caveat":"measured by libane on the MIL path only; Path B is said to honour the offset","contested":false}
{"id":"API-032","claim":"The ANE hardware requires a minimum IOSurface allocation of roughly 49 KB for evaluation, so small tensors must be padded.","kind":"gotcha","confidence":"claimed","source":"https://arxiv.org/abs/2603.06728","source_type":"primary","retrieved":"2026-09-23","topic":["api","memory","gotchas"],"entities":["IOSurface","Orion"],"evidence":"shape [1,768,1,1] in fp16 is 3072 bytes and must be padded to at least [1,768,1,16] = 24576 bytes","caveat":"reported by Orion; the exact threshold is stated as approximately 49 KB","contested":false}
{"id":"API-033","claim":"_ANEClient is the daemon-facing client class whose sharedConnection class method returns a process-wide instance.","kind":"definition","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/src/runtime/ane_runtime.mm","source_type":"primary","retrieved":"2026-09-23","topic":["api","classes"],"entities":["_ANEClient","sharedConnection"],"contested":false}
{"id":"API-034","claim":"-initWithRestrictedAccessAllowed: is the _ANEClient initialiser used by ane-infer to obtain a direct client, called with YES.","kind":"procedure","confidence":"measured","source":"https://github.com/thebasedcapital/ane-infer/blob/main/crates/ane-bridge/objc/ane_runtime.m","source_type":"primary","retrieved":"2026-09-23","topic":["api","procedure"],"entities":["_ANEClient","initWithRestrictedAccessAllowed:"],"contested":false}
{"id":"API-035","claim":"The modern _ANEClient direct evaluation selector takes five arguments: doEvaluateDirectWithModel:options:request:qos:error:.","kind":"fact","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/src/runtime/ane_runtime.mm","source_type":"primary","retrieved":"2026-09-23","topic":["api","signatures"],"entities":["_ANEClient","doEvaluateDirectWithModel:options:request:qos:error:"],"contested":false,"split":"holdout"}
{"id":"API-036","claim":"An older iOS-era header records the direct evaluation selector as the four-argument doEvaluateDirectWithModel:request:qos:error: without an options argument.","kind":"fact","confidence":"documented","source":"https://github.com/nst/iOS-Runtime-Headers/blob/master/PrivateFrameworks/AppleNeuralEngine.framework/_ANEClient.h","source_type":"primary","retrieved":"2026-09-23","topic":["api","signatures","versioning"],"entities":["_ANEClient","doEvaluateDirectWithModel:request:qos:error:"],"caveat":"old iOS dump, predates the in-memory-model API","contested":false}
{"id":"API-037","claim":"The current class dump contains no class named _ANECompiler even though project prose and Orion's API table refer to one.","kind":"open-question","confidence":"documented","source":"https://github.com/tmc/apple/tree/main/private/appleneuralengine","source_type":"secondary","retrieved":"2026-09-23","topic":["api","contested"],"entities":["_ANECompiler"],"evidence":"no *_compiler_.gen.go file exists; only _ANECompilerServiceProtocol does","caveat":"absence in one generated dump is not proof of non-existence, but four working codebases also never reference such a class","contested":true}
{"id":"API-038","claim":"The string _ANECompiler : ANECCompile() FAILED is an error message emitted by the compile service rather than an indication that a class named _ANECompiler was called.","kind":"gotcha","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/coreai-model-zoo/knowledge/coreai-error-index.md","source_type":"our-own","retrieved":"2026-09-23","topic":["api","errors"],"entities":["_ANECompiler","ANECCompile","com.apple.appleneuralengine.compiler"],"evidence":"Error Domain=com.apple.appleneuralengine.compiler Code=1 \"_ANECompiler : ANECCompile() FAILED\"","contested":false}
{"id":"API-039","claim":"The class name _ANEMemoryModel named in some briefs appears in no class dump, no working codebase and no paper that was examined.","kind":"open-question","confidence":"inferred","source":"https://github.com/tmc/apple/tree/main/private/appleneuralengine","source_type":"secondary","retrieved":"2026-09-23","topic":["api","open-questions"],"entities":["_ANEMemoryModel"],"caveat":"absence of evidence gathered on 2026-09-23","contested":false}
{"id":"API-040","claim":"The class inventory of the current framework includes _ANEWeight, _ANEModelToken, _ANEProcedureData, _ANEVirtualClient, _ANEModelInstanceParameters, _ANEProgramIOSurfacesMapper and _ANEPerformanceStats beyond the classes used by public projects.","kind":"fact","confidence":"documented","source":"https://github.com/tmc/apple/tree/main/private/appleneuralengine","source_type":"secondary","retrieved":"2026-09-23","topic":["api","classes"],"entities":["_ANEWeight","_ANEModelToken","_ANEProcedureData","_ANEVirtualClient"],"contested":false}
{"id":"API-041","claim":"_ANEProgramForEvaluation exposes processRequest:model:qos:qIndex:modelStringID:options:returnValue:error: as a direct dispatch path.","kind":"fact","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/src/runtime/ane_runtime.mm","source_type":"primary","retrieved":"2026-09-23","topic":["api","signatures"],"entities":["_ANEProgramForEvaluation","processRequest:"],"contested":false}
{"id":"API-042","claim":"processRequest: measured 0.365 ms per evaluation versus 0.413 ms for evaluateWithQoS:, about 13 percent lower latency.","kind":"measurement","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/docs/ane-runtime-boundary.md","source_type":"primary","retrieved":"2026-09-23","topic":["performance","dispatch"],"entities":["processRequest:","evaluateWithQoS:","libane"],"evidence":"0.365 vs 0.413 ms/eval","caveat":"hardware and model size not restated in the document","contested":false,"split":"holdout"}
{"id":"API-043","claim":"Delegate calls with a do prefix bypass the ANE daemon XPC hop and reach the kernel driver directly.","kind":"fact","confidence":"claimed","source":"https://github.com/thebasedcapital/ane-infer/blob/main/docs/ane-internals.md","source_type":"primary","retrieved":"2026-09-23","topic":["api","dispatch"],"entities":["doEvaluateDirectWithModel:","doLoadModel:","XPC"],"contested":false}
{"id":"API-044","claim":"ane-infer measured direct evaluation at 106 microseconds versus 117 microseconds for the standard path, a claimed 10 percent improvement.","kind":"measurement","confidence":"measured","source":"https://github.com/thebasedcapital/ane-infer/blob/main/docs/ane-internals.md","source_type":"primary","retrieved":"2026-09-23","topic":["performance","dispatch"],"entities":["doEvaluateDirectWithModel:","evaluateWithQoS:","ane-infer"],"contested":true}
{"id":"API-045","claim":"libane measured doEvaluateDirectWithModel: on the MIL path at 401 microseconds p50, 18 percent slower than processRequest: at 346 microseconds p50.","kind":"measurement","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/src/runtime/ane_runtime.mm","source_type":"primary","retrieved":"2026-09-23","topic":["performance","dispatch"],"entities":["doEvaluateDirectWithModel:","processRequest:","libane"],"evidence":"libane argues the earlier 37 percent claim compared against CoreML's evaluateWithModel: rather than processRequest:","contested":true}
{"id":"API-046","claim":"_ANEDeviceInfo exposes only class methods and must be called on the Class object rather than on an allocated instance.","kind":"gotcha","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/src/runtime/ane_runtime.mm","source_type":"primary","retrieved":"2026-09-23","topic":["api","gotchas"],"entities":["_ANEDeviceInfo"],"contested":false}
{"id":"API-047","claim":"+aneArchitectureType on _ANEDeviceInfo returns a short architecture string such as h15g on M3 and h16g on M4.","kind":"fact","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/src/runtime/ane_runtime.mm","source_type":"primary","retrieved":"2026-09-23","topic":["api","hardware"],"entities":["_ANEDeviceInfo","aneArchitectureType","M3","M4"],"contested":false}
{"id":"API-048","claim":"_ANEDeviceInfo provides class methods +numANECores and +numANEs returning the inference core count and ANE unit count.","kind":"fact","confidence":"documented","source":"https://github.com/tmc/apple/blob/main/private/appleneuralengine/ane_device_info.gen.go","source_type":"secondary","retrieved":"2026-09-23","topic":["api","hardware"],"entities":["_ANEDeviceInfo","numANECores","numANEs"],"contested":false}
{"id":"API-049","claim":"_ANEDeviceController holds the device connection for a program handle and exposes start and stop plus a raw three-pointer device struct.","kind":"definition","confidence":"documented","source":"https://github.com/tmc/apple/blob/main/private/appleneuralengine/ane_device_controller.gen.go","source_type":"secondary","retrieved":"2026-09-23","topic":["api","classes"],"entities":["_ANEDeviceController","ANEDeviceStruct"],"contested":false}
{"id":"API-050","claim":"_ANEDeviceController has an initialiser spelled initWithProgramHandle:priviledged: with priviledged misspelled in the selector.","kind":"gotcha","confidence":"documented","source":"https://github.com/AmiraniLabs/libane/blob/main/src/runtime/ane_runtime.mm","source_type":"secondary","retrieved":"2026-09-23","topic":["api","gotchas"],"entities":["_ANEDeviceController","initWithProgramHandle:priviledged:"],"contested":false}
{"id":"API-051","claim":"_ANEQoSMapper maps QoS values to program priority and queue index and exposes +queueIndexForQoS: and +programPriorityForQoS:.","kind":"fact","confidence":"documented","source":"https://github.com/tmc/apple/blob/main/private/appleneuralengine/ane_qo_s_mapper.gen.go","source_type":"secondary","retrieved":"2026-09-23","topic":["api"],"entities":["_ANEQoSMapper"],"contested":false}
{"id":"API-052","claim":"_ANEStrings centralises framework constants including error domains, entitlement names, mach service names and default file names such as the MIL, MLIR, ANECIR, hwx and weight file names.","kind":"definition","confidence":"documented","source":"https://github.com/tmc/apple/blob/main/private/appleneuralengine/ane_strings.gen.go","source_type":"secondary","retrieved":"2026-09-23","topic":["api","classes"],"entities":["_ANEStrings"],"contested":false}
{"id":"API-053","claim":"_ANEErrors provides one error factory per failure class, including programCreationErrorForMethod:, programLoadErrorForMethod:, entitlementErrorForMethod: and programIOSurfacesMapErrorForMethod:code:.","kind":"definition","confidence":"documented","source":"https://github.com/tmc/apple/blob/main/private/appleneuralengine/ane_errors.gen.go","source_type":"secondary","retrieved":"2026-09-23","topic":["api","errors"],"entities":["_ANEErrors"],"contested":false}
{"id":"API-054","claim":"libane attributes the Path A failure Program IOSurfaces map failure with error 13 or 0x12 to the missing intermediateBufferHandle.","kind":"measurement","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/docs/ane-runtime-boundary.md","source_type":"primary","retrieved":"2026-09-23","topic":["api","errors"],"entities":["mapIOSurfacesWithRequest:cacheInference:","intermediateBufferHandle"],"evidence":"error is identical whether or not the IOSurface objects carry a non-zero startOffset","caveat":"reported by one project","contested":false}
{"id":"API-055","claim":"The canonical in-memory execution sequence is: create descriptor, create model, get hexStringIdentifier, write model.mil and weights into the temp directory, compileWithQoS:, loadWithQoS:, build IOSurfaces and a request, then evaluateWithQoS:.","kind":"procedure","confidence":"measured","source":"https://github.com/maderix/ANE/blob/main/bridge/ane_bridge.m","source_type":"primary","retrieved":"2026-09-23","topic":["api","procedure"],"entities":["_ANEInMemoryModel","_ANEInMemoryModelDescriptor","_ANERequest"],"contested":false,"split":"holdout"}
{"id":"API-056","claim":"The ANE weight blob format begins with byte 0x01, then 0x02 at offset 4, the magic EF BE AD DE at offset 64, 0x01 at offset 68, the fp16 payload size as a uint32 at offset 72, the constant 128 as a uint32 at offset 80, and the fp16 weights from offset 128.","kind":"definition","confidence":"measured","source":"https://github.com/maderix/ANE/blob/main/bridge/ane_bridge.m","source_type":"primary","retrieved":"2026-09-23","topic":["program-format","weights"],"entities":["BLOBFILE"],"evidence":"byte-identical layout independently implemented in maderix/ANE and ANE-LM","contested":false}
{"id":"API-057","claim":"The BLOBFILE weight offset must be uint64(64) rather than 128 or weight loading silently produces garbage.","kind":"gotcha","confidence":"claimed","source":"https://arxiv.org/abs/2603.06728","source_type":"primary","retrieved":"2026-09-23","topic":["program-format","gotchas"],"entities":["BLOBFILE","Orion"],"caveat":"stated as Orion constraint #8; maderix and ANE-LM code use the same offset","contested":false}
{"id":"API-058","claim":"ANE-LM caches compiled models with a marker file in ~/Library/Caches/ane_lm/compiled_markers and skips compileWithQoS: when the marker exists, calling only loadWithQoS:.","kind":"procedure","confidence":"measured","source":"https://github.com/johnmai-dev/ANE-LM/blob/main/core/ane_runtime.cpp","source_type":"primary","retrieved":"2026-09-23","topic":["api","procedure","caching"],"entities":["ANE-LM","compileWithQoS:","loadWithQoS:"],"contested":false}
{"id":"API-059","claim":"maderix retries loadWithQoS: once after a 100 ms pause when the first load fails, attributing the failure to ANE slot reclamation.","kind":"procedure","confidence":"measured","source":"https://github.com/maderix/ANE/blob/main/bridge/ane_bridge.m","source_type":"primary","retrieved":"2026-09-23","topic":["api","procedure"],"entities":["maderix/ANE","loadWithQoS:"],"caveat":"the reclamation explanation is the author's comment, not a measured result","contested":false}
{"id":"API-060","claim":"The current framework class dump lists about ninety classes and protocols for AppleNeuralEngine, matching the set that working projects resolve by name.","kind":"fact","confidence":"documented","source":"https://github.com/tmc/apple/tree/main/private/appleneuralengine","source_type":"secondary","retrieved":"2026-09-23","topic":["api","classes"],"entities":["AppleNeuralEngine.framework"],"caveat":"generated bindings; generation method is described as automatic from Apple documentation and was not independently audited","contested":false}
{"id":"API-061","claim":"Programs cross the language boundary by compiling a small Objective-C shim to a dylib that exposes plain C functions, which Python ctypes, Rust FFI or Swift then call.","kind":"procedure","confidence":"measured","source":"https://github.com/maderix/ANE/blob/main/bridge/ane_bridge.h","source_type":"primary","retrieved":"2026-09-23","topic":["api","bindings"],"entities":["ane_bridge","ctypes"],"contested":false}
{"id":"API-062","claim":"The ANE ObjC runtime calls are made without any private headers by declaring the argument types through objc_msgSend function-pointer casts, as ANE-LM does with sel_registerName.","kind":"procedure","confidence":"measured","source":"https://github.com/johnmai-dev/ANE-LM/blob/main/core/ane_runtime.cpp","source_type":"primary","retrieved":"2026-09-23","topic":["api","bindings"],"entities":["objc_msgSend","sel_registerName","ANE-LM"],"caveat":"a wrong cast produces silent corruption rather than a compile error","contested":false}
{"id":"API-063","claim":"ANE bridge code must be compiled with -fno-objc-arc because ARC cannot manage the id fields held inside the C kernel handle structs.","kind":"gotcha","confidence":"measured","source":"https://github.com/thebasedcapital/ane-infer/blob/main/crates/ane-bridge/build.rs","source_type":"primary","retrieved":"2026-09-23","topic":["api","bindings"],"entities":["ane-infer","Rust","ARC"],"contested":false}
{"id":"API-064","claim":"The Go package github.com/tmc/apple/private/appleneuralengine binds the whole framework cgo-free with purego and is the most complete public inventory of its class and method surface.","kind":"fact","confidence":"documented","source":"https://github.com/tmc/apple/tree/main/private/appleneuralengine","source_type":"secondary","retrieved":"2026-09-23","topic":["api","bindings"],"entities":["tmc/apple","purego","Go"],"caveat":"no report was found of anyone running these bindings successfully","contested":false}
{"id":"API-065","claim":"_ANEInMemoryModel exposes mapIOSurfacesWithRequest:cacheInference:error: and unmapIOSurfacesWithRequest: on the model object itself, in parallel with the _ANEClient versions.","kind":"fact","confidence":"documented","source":"https://github.com/tmc/apple/blob/main/private/appleneuralengine/ane_in_memory_model.gen.go","source_type":"secondary","retrieved":"2026-09-23","topic":["api","signatures"],"entities":["_ANEInMemoryModel","mapIOSurfacesWithRequest:cacheInference:error:"],"contested":false}
{"id":"API-066","claim":"On Path B a compiled .mlmodelc is loaded by calling _ANEClient compileModel:options:qos:error: then loadModel:options:qos:error: on an _ANEModel built with modelAtURL:key:.","kind":"procedure","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/src/runtime/ane_runtime.mm","source_type":"primary","retrieved":"2026-09-23","topic":["api","procedure"],"entities":["_ANEClient","_ANEModel","libane"],"contested":false,"split":"holdout"}
{"id":"API-067","claim":"Path B registers IOSurfaces once with _ANEClient mapIOSurfacesWithModel:request:cacheInference:error: passing cacheInference YES, after which doEvaluateDirectWithModel: uses the cached fast connection.","kind":"procedure","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/src/runtime/ane_runtime.mm","source_type":"primary","retrieved":"2026-09-23","topic":["api","procedure","performance"],"entities":["mapIOSurfacesWithModel:request:cacheInference:error:","fastConn"],"contested":false}
{"id":"API-068","claim":"Path B tensor layout strides can be read authoritatively from modelAttributes at networkStatusList[0] liveInputList and liveOutputList entries, which carry batchStride and planeStride.","kind":"procedure","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/src/runtime/ane_runtime.mm","source_type":"primary","retrieved":"2026-09-23","topic":["api","memory","layout"],"entities":["modelAttributes","planeStride","batchStride"],"contested":false}
{"id":"API-069","claim":"The ANE requires 64-byte plane alignment, so a plane stride is round64(sequence_length * 2) bytes for fp16 data.","kind":"gotcha","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/src/runtime/ane_runtime.mm","source_type":"primary","retrieved":"2026-09-23","topic":["memory","layout","gotchas"],"entities":["planeStride","fp16"],"caveat":"libane states it as a fallback rule when modelAttributes KVC fails","contested":false}
{"id":"API-070","claim":"Multi-function MIL programs are addressable through the procedureIndex argument of the request factory, with the compiled model reporting ANEFModelProcedures and ProcedureNameToIDMap inside modelAttributes.","kind":"fact","confidence":"measured","source":"https://github.com/thebasedcapital/ane-infer/blob/main/docs/ane-internals.md","source_type":"primary","retrieved":"2026-09-23","topic":["api","multi-procedure"],"entities":["procedureIndex","ANEFModelProcedures","ane-infer"],"contested":false}
{"id":"API-071","claim":"In a multi-procedure model, procedure N uses inputIndex N and outputIndex N rather than index 0, and using the wrong indices returns error 0x2.","kind":"gotcha","confidence":"measured","source":"https://github.com/thebasedcapital/ane-infer/blob/main/docs/ane-internals.md","source_type":"primary","retrieved":"2026-09-23","topic":["api","gotchas","multi-procedure"],"entities":["procedureIndex","ane-infer"],"contested":false,"split":"holdout"}
{"id":"API-072","claim":"Multi-input and multi-output ANE programs require all input surfaces to share one allocation size and all output surfaces to share another.","kind":"gotcha","confidence":"claimed","source":"https://arxiv.org/abs/2603.06728","source_type":"primary","retrieved":"2026-09-23","topic":["memory","gotchas"],"entities":["IOSurface","Orion"],"evidence":"Orion constraints #2 and #18, symptom error 0x1d at eval","caveat":"contradicted by the claim that multi-input requests always fail; see the contested record API-073","contested":false}
{"id":"API-073","claim":"Sources disagree on whether multi-input ANE programs work: libane and ane-infer build multi-input requests while maderix and our own sweep state that multi-input requests error and that inputs must be packed into one surface's spatial dimension.","kind":"open-question","confidence":"claimed","source":"/Volumes/data/local_ai_stack/results/RESEARCH-SWEEP.md","source_type":"our-own","retrieved":"2026-09-23","topic":["api","contested"],"entities":["maderix/ANE","libane","ane-infer"],"contested":true}
{"id":"API-074","claim":"Multi-input surfaces must be ordered alphabetically by their MIL parameter name and multi-output surfaces by their MIL variable name, or the ANE silently reads or writes the wrong tensors.","kind":"gotcha","confidence":"claimed","source":"https://arxiv.org/abs/2603.06728","source_type":"primary","retrieved":"2026-09-23","topic":["memory","gotchas"],"entities":["Orion","libane"],"evidence":"libane implements the same alphabetical reordering and calls it constraints 13 and 3","caveat":"implemented defensively by libane; not independently measured as a failure mode here","contested":false}
{"id":"API-075","claim":"Sources disagree on whether compiled ANE weights can be replaced without recompiling: Orion reports patching the weight files on disk and reloading reduces per-step cost from 4200 ms to 494 ms, while libane states that rewriting weight blobs before loadWithQoS: has zero effect.","kind":"open-question","confidence":"measured","source":"https://arxiv.org/abs/2603.06728","source_type":"primary","retrieved":"2026-09-23","topic":["weights","contested","performance"],"entities":["Orion","libane","delta compilation"],"contested":true}
{"id":"API-076","claim":"libane's probe_delta_reload concluded on 2026-04-16 that ANE bakes weights into the compiled HWX at compileWithQoS: time and that weight values cannot change without a full recompile.","kind":"measurement","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/src/runtime/ane_runtime.mm","source_type":"primary","retrieved":"2026-09-23","topic":["weights"],"entities":["libane","compileWithQoS:"],"contested":true}
{"id":"API-077","claim":"maderix ships test_weight_patch.m and test_weight_reload.m that specifically probe whether weights can be patched on disk or in memory after compilation, but the repository records no verdict in the source.","kind":"fact","confidence":"measured","source":"https://github.com/maderix/ANE/blob/main/training/test_weight_reload.m","source_type":"primary","retrieved":"2026-09-23","topic":["weights","open-questions"],"entities":["maderix/ANE"],"contested":false}
{"id":"API-078","claim":"maderix avoids recompilation in production by packing weights into the spatial dimension of inputs so one compiled kernel serves all layers.","kind":"procedure","confidence":"measured","source":"https://github.com/maderix/ANE/blob/main/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["weights","performance"],"entities":["maderix/ANE","dynamic pipeline"],"contested":false}
{"id":"API-079","claim":"_ANEIOSurfaceOutputSets is created by +objectWithstatsSurRef:outputBuffer: and the non-existent alternative +outputSetsWithBuffers: causes error 15 when used.","kind":"gotcha","confidence":"measured","source":"https://github.com/thebasedcapital/ane-infer/blob/main/docs/ane-internals.md","source_type":"primary","retrieved":"2026-09-23","topic":["api","chaining","gotchas"],"entities":["_ANEIOSurfaceOutputSets"],"contested":false}
{"id":"API-080","claim":"_ANEChainingRequest is built with +chainingRequestWithInputs:outputSets:lbInputSymbolId:lbOutputSymbolId:procedureIndex:signalEvents:transactionHandle:fwEnqueueDelay:memoryPoolId:.","kind":"fact","confidence":"measured","source":"https://github.com/thebasedcapital/ane-infer/blob/main/docs/ane-internals.md","source_type":"primary","retrieved":"2026-09-23","topic":["api","chaining","signatures"],"entities":["_ANEChainingRequest"],"evidence":"confirmed independently by the generated binding +chainingRequestWithInputs:outputSets:lbInputSymbolId:lbOutputSymbolId:procedureIndex:signalEvents:transactionHandle:fwEnqueueDelay:memoryPoolId:","contested":false}
{"id":"API-081","claim":"ane-infer reports that prepareChainingWithModel: succeeds but buffersReadyWithModel: fails silently and that the chaining sequence cannot skip steps.","kind":"measurement","confidence":"measured","source":"https://github.com/thebasedcapital/ane-infer/blob/main/docs/ane-internals.md","source_type":"primary","retrieved":"2026-09-23","topic":["api","chaining"],"entities":["prepareChainingWithModel:","buffersReadyWithModel:","ane-infer"],"contested":false,"split":"holdout"}
{"id":"API-082","claim":"libane reports that chaining via _ANEChainingRequest is unreachable from the MIL path with error 15, caused by a zero intermediateBufferHandle.","kind":"measurement","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/docs/ane-runtime-boundary.md","source_type":"primary","retrieved":"2026-09-23","topic":["api","chaining","contested"],"entities":["_ANEChainingRequest","intermediateBufferHandle"],"contested":false}
{"id":"API-083","claim":"_ANESharedEvents signal or wait events on the MIL path crash with EXC_BAD_ACCESS at address 0x10 inside the processRequest: completion block because a nil C++ event infrastructure pointer is virtually dispatched.","kind":"gotcha","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/docs/ane-runtime-boundary.md","source_type":"primary","retrieved":"2026-09-23","topic":["api","crashes"],"entities":["_ANESharedEvents","processRequest:","libane"],"evidence":"crash frame -[_ANEProgramForEvaluation processRequest:...]_block_invoke + 1320; an empty shared-events pair does not crash","caveat":"observed on the MIL path; the same mechanism is reported to work when intermediateBufferHandle is non-zero","contested":false}
{"id":"API-084","claim":"No public source decodes the ANE performance stats buffer: its field layout, units and the meaning of perfStatsMask bits are unpublished.","kind":"open-question","confidence":"inferred","source":"https://github.com/tmc/apple/blob/main/private/appleneuralengine/ane_performance_stats.gen.go","source_type":"secondary","retrieved":"2026-09-23","topic":["api","open-questions"],"entities":["_ANEPerformanceStats","perfStatsMask"],"caveat":"based on the sources examined on 2026-09-23; the only concrete value seen was perfStatsMask=0 in an lldb capture","contested":false}
{"id":"API-085","claim":"The observed value queueDepth 127 on loaded ANE models is unexplained in all public sources.","kind":"open-question","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/docs/ane-runtime-boundary.md","source_type":"primary","retrieved":"2026-09-23","topic":["api","open-questions"],"entities":["queueDepth"],"caveat":"plausibly the maximum in-flight evaluations but nothing states this","contested":false}
{"id":"API-086","claim":"Only two values of the ANE model state field have been observed publicly: 1 for an unloaded model and 3 for a loaded model.","kind":"measurement","confidence":"measured","source":"https://github.com/thebasedcapital/ane-infer/blob/main/docs/ane-internals.md","source_type":"primary","retrieved":"2026-09-23","topic":["api","open-questions"],"entities":["_ANEModel","state"],"evidence":"state=1 in a live _ANEModel capture via lldb; '[+96] uint64 _state (3 = loaded)' in ane-infer's ivar table","caveat":"the rest of the enum is unknown","contested":false}
{"id":"API-087","claim":"ane-infer published an ivar offset table for _ANEInMemoryModel including offsets +8 queueDepth, +32 intermediateBufferHandle, +64 _ANEModel, +88 _ANEProgramForEvaluation and +96 state.","kind":"measurement","confidence":"measured","source":"https://github.com/thebasedcapital/ane-infer/blob/main/docs/ane-internals.md","source_type":"primary","retrieved":"2026-09-23","topic":["api","internals"],"entities":["_ANEInMemoryModel","ane-infer"],"caveat":"single source, unpublished elsewhere; ivar offsets change between OS builds and only the field names could be cross-checked","contested":false}
{"id":"API-088","claim":"Every project reaches the loaded program object by KVC through _ANEInMemoryModel model and program keys rather than through public accessors.","kind":"procedure","confidence":"measured","source":"https://github.com/AmiraniLabs/libane/blob/main/src/runtime/ane_runtime.mm","source_type":"primary","retrieved":"2026-09-23","topic":["api","procedure"],"entities":["valueForKey:","_ANEProgramForEvaluation"],"contested":false}
{"id":"API-089","claim":"Modern macOS AppleNeuralEngine class and method names must be treated as unstable because the iOS header dump and the current dump differ in both class set and method signatures.","kind":"gotcha","confidence":"documented","source":"https://github.com/nst/iOS-Runtime-Headers/blob/master/PrivateFrameworks/AppleNeuralEngine.framework/_ANEClient.h","source_type":"primary","retrieved":"2026-09-23","topic":["api","versioning"],"entities":["iOS-Runtime-Headers","tmc/apple"],"evidence":"_ANEInMemoryModel and the entire in-memory API are absent from the iOS dump, and doEvaluateDirectWithModel: gained an options argument","contested":false}
{"id":"API-090","claim":"Core ML dispatches ANE work through Espresso, whose plan and context are opaque C++ pointers inside MLNeuralNetworkEngine, so Core ML models and private-API models use separate compilation and dispatch pipelines to the same hardware.","kind":"fact","confidence":"claimed","source":"https://github.com/thebasedcapital/ane-infer/blob/main/docs/ane-internals.md","source_type":"primary","retrieved":"2026-09-23","topic":["architecture","coreml"],"entities":["Espresso","MLNeuralNetworkEngine","CoreML"],"caveat":"the pipeline separation is an inference drawn by ane-infer from ivar inspection, not a documented fact","contested":false}
{"id":"API-091","claim":"tinygrad's ANE work predates the framework API and calls the H11ANE kernel driver directly with ANE_ProgramCreate, ANE_ProgramPrepare and ANE_ProgramSendRequest.","kind":"fact","confidence":"measured","source":"https://github.com/tinygrad/tinygrad/blob/d0e752003da3fc023fa85094d7f5b65b47dd5091/extra/accel/ane/lib/ane.mm","source_type":"primary","retrieved":"2026-09-23","topic":["api","iokit"],"entities":["H11ANE","tinygrad"],"contested":false}
{"id":"API-092","claim":"Setting a breakpoint on -[_ANEModel program] and seeing it hit means Core ML is dispatching that model to the ANE, though not necessarily the whole model.","kind":"procedure","confidence":"documented","source":"/Volumes/data/local_ai_stack/repos/neural-engine/docs/is-model-using-ane.md","source_type":"primary","retrieved":"2026-09-23","topic":["api","debugging"],"entities":["_ANEModel","CoreML"],"contested":false}
{"id":"API-093","claim":"The direct H11ANE IOKit path originally required disabling AMFI or runtime-patching amfid, whereas the framework path requires no such modification.","kind":"gotcha","confidence":"measured","source":"https://github.com/tinygrad/tinygrad/blob/d0e752003da3fc023fa85094d7f5b65b47dd5091/extra/accel/ane/README.md","source_type":"primary","retrieved":"2026-09-23","topic":["api","entitlements"],"entities":["AMFI","amfid","tinygrad"],"caveat":"documented for macOS 12.4 in that README","contested":false}
{"id":"API-094","claim":"The ANE dispatch overhead through XPC and IOKit is about 0.095 ms per evaluation.","kind":"measurement","confidence":"measured","source":"https://arxiv.org/abs/2603.06728","source_type":"primary","retrieved":"2026-09-23","topic":["performance","dispatch"],"entities":["Orion","XPC","IOKit"],"caveat":"measured on M4 Max and attributed to prior maderix work","contested":false}
{"id":"API-095","claim":"The ANE compiler accepts only a subset of MIL operations, rejecting concat outright and requiring gelu to be replaced by its tanh approximation.","kind":"gotcha","confidence":"claimed","source":"https://arxiv.org/abs/2603.06728","source_type":"primary","retrieved":"2026-09-23","topic":["compilation","gotchas"],"entities":["MIL","Orion","concat","gelu"],"caveat":"from Orion's self-reported constraint catalog; MIL op support varies with OS and compiler build","contested":false}
{"id":"API-096","claim":"Approximately 119 compilations are possible per process before subsequent compilations silently fail, which projects work around by re-executing the process or by avoiding recompilation.","kind":"measurement","confidence":"measured","source":"https://arxiv.org/abs/2603.06728","source_type":"primary","retrieved":"2026-09-23","topic":["compilation","gotchas"],"entities":["Orion","maderix/ANE"],"evidence":"maderix/ANE README lists exec() restart as its bypass; Orion measured roughly 119 compilations per process","caveat":"value is approximate and may vary with model size and OS build","contested":false,"split":"holdout"}
{"id":"API-097","claim":"A generated Go binding set exists that enumerates every AppleNeuralEngine class and method, making it the fastest way to check whether a selector exists although its selector colon placement is reconstructed rather than copied from a header.","kind":"gotcha","confidence":"documented","source":"https://github.com/tmc/apple/tree/main/private/appleneuralengine","source_type":"secondary","retrieved":"2026-09-23","topic":["api","sources"],"entities":["tmc/apple"],"caveat":"the generator's method naming is mechanical; treat argument structure as probable not certain","contested":false}
{"id":"API-098","claim":"_ANEIOSurfaceObject class methods include createIOSurfaceWithWidth:pixel_size:height: and a bytesPerElement variant, offering an ANE-side convenience allocator.","kind":"fact","confidence":"documented","source":"https://github.com/tmc/apple/blob/main/private/appleneuralengine/aneio_surface_object.gen.go","source_type":"secondary","retrieved":"2026-09-23","topic":["api","signatures"],"entities":["_ANEIOSurfaceObject"],"caveat":"not used by any of the four working projects, which call IOSurfaceCreate directly","contested":false}
{"id":"API-099","claim":"Public projects allocate I/O surfaces manually with IOSurfaceCreate using width equal to the byte size, height 1, bytesPerElement 1, bytesPerRow equal to the byte size, allocSize equal to the byte size and pixelFormat 0.","kind":"procedure","confidence":"measured","source":"https://github.com/maderix/ANE/blob/main/bridge/ane_bridge.m","source_type":"primary","retrieved":"2026-09-23","topic":["memory","procedure"],"entities":["IOSurfaceCreate"],"evidence":"identical dictionary in maderix/ANE and ane-infer","contested":false}
{"id":"API-100","claim":"The ANE reads a flat input buffer as packed [1,C,1,S] data starting at byte 0, ignoring the surface's nominal width and height.","kind":"gotcha","confidence":"claimed","source":"https://arxiv.org/abs/2603.06728","source_type":"primary","retrieved":"2026-09-23","topic":["memory","layout"],"entities":["IOSurface","Orion"],"evidence":"Orion constraint #20; consistent with libane's flat-pack write and channel-first conventions in maderix and ANE-LM","contested":false}
{"id":"API-101","claim":"On macOS 27.0.1 (M5 Max, Mac17,14) the AppleNeuralEngine runtime contains exactly three shared-event classes: _ANESharedWaitEvent, _ANESharedSignalEvent and _ANESharedEvents.","kind":"fact","confidence":"measured","source":"results/EXP-025-ane-gpu-sync/results/class_dump.txt","source_type":"our-own","retrieved":"2026-10-07","topic":["api","classes","shared-events"],"entities":["_ANESharedEvents","_ANESharedSignalEvent","_ANESharedWaitEvent","macOS 27.0.1","M5 Max"],"evidence":"runtime scan of 10398 classes image-filtered to AppleNeuralEngine.framework returned exactly 3 matches","contested":false}
{"id":"API-102","claim":"_ANESharedWaitEvent and _ANESharedSignalEvent hold their counter in a _sharedEvent ivar of type IOSurfaceSharedEvent, a runtime-only class absent from the macOS 27 SDK headers; _ANESharedEvents holds _signalEvents and _waitEvents NSArray containers.","kind":"fact","confidence":"measured","source":"results/EXP-025-ane-gpu-sync/results/class_dump.txt","source_type":"our-own","retrieved":"2026-10-07","topic":["api","classes","shared-events"],"entities":["_ANESharedEvents","IOSurfaceSharedEvent"],"evidence":"ivar encoding @\"IOSurfaceSharedEvent\" in class dump; no method or ivar in the trio mentions Metal; AppleNeuralEngine and aned link IOSurface+IOKit but not Metal (otool -L)","contested":false}
{"id":"API-103","claim":"MTLSharedEvent and the ANE shared-event classes are two ObjC wrappers over one kernel event object: MTLSharedEventHandle.eventPort fed to [IOSurfaceSharedEvent initWithMachPort:] yields a shared counter on which a GPU encodeSignalEvent: unblocked a wrapper-side waitUntilSignaledValue: in ~62 microseconds, bidirectionally.","kind":"measurement","confidence":"measured","source":"results/EXP-025-ane-gpu-sync/results/porttest.txt","source_type":"our-own","retrieved":"2026-10-07","topic":["api","shared-events","performance","metal"],"entities":["MTLSharedEvent","IOSurfaceSharedEvent","eventPort","encodeSignalEvent:"],"evidence":"porttest T2 gpu commit->wait 62us, T3 wrapper-signal->MTLSharedEvent value=3; lldb shows eventPort 12339 identical through both API families","caveat":"measured in our own process on this Studio; no entitlement required","contested":false}
{"id":"API-104","claim":"ANE eval dispatch reads -[_ANERequest sharedEvents] exactly four times per processRequest: call, making shared events a first-class input of the dispatch path.","kind":"measurement","confidence":"measured","source":"results/EXP-025-ane-gpu-sync/results/dtrace_ane_methods.txt.gz","source_type":"our-own","retrieved":"2026-10-07","topic":["api","shared-events","dispatch"],"entities":["_ANERequest","sharedEvents","processRequest:"],"evidence":"pid-provider dtrace on our own harness: 6744 sharedEvents reads / 1686 processRequest evaluations = 4.0","contested":false}
{"id":"API-105","claim":"A live _ANESharedSignalEvent instance exposes ivars value, symbolIndex, eventType, agentMask and sharedEvent at raw offsets +8/+16/+24/+32/+40 matching the class-dump encodings (observed value=42 symbolIndex=7 eventType=1 agentMask=1).","kind":"measurement","confidence":"measured","source":"results/EXP-025-ane-gpu-sync/results/lldb_shared_events.txt","source_type":"our-own","retrieved":"2026-10-07","topic":["api","shared-events","internals"],"entities":["_ANESharedSignalEvent"],"caveat":"semantics of symbolIndex, eventType and agentMask remain unproven; firmware wait-loop not disassembled (SIP blocks aned attach)","contested":false}
{"id":"API-106","claim":"On the in-memory-MIL path (Path A) attaching a populated _ANESharedEvents to an _ANERequest crashes deterministically at -[_ANEProgramForEvaluation processRequest:...block_invoke +1524] with fault address 0x10 on macOS 27.0.1 / M5 Max.","kind":"gotcha","confidence":"measured","source":"results/EXP-025-ane-gpu-sync/VERDICT.md","source_type":"our-own","retrieved":"2026-10-07","topic":["api","shared-events","crashes"],"entities":["_ANESharedEvents","processRequest:","_ANERequest"],"evidence":"reproduced independently of libane's report (API-083) in the ane-sync harness; pack FAILURES F11/F14","contested":false}
{"id":"API-107","claim":"The tmc/apple Go bindings guard the shared-events path with ErrSharedEventRequiresPackage - shared events require package-backed models (ModelTypePackage), in-memory MIL returning an error - and expose kANEFDisableIOFencesUseSharedEventsKey and kANEFEnableFWToFWSignal option keys, implying default eval fencing is IOSurface IOFences with shared events opt-in.","kind":"fact","confidence":"documented","source":"https://pkg.go.dev/github.com/tmc/apple/x/ane","source_type":"primary","retrieved":"2026-10-07","topic":["api","shared-events","gating"],"entities":["tmc/apple","ModelTypePackage","kANEFDisableIOFencesUseSharedEvents","kANEFEnableFWToFWSignal"],"evidence":"independent corroboration of the Path-A crash (API-106) and the Path-B intermediateBufferHandle gate; on-disk strings of the framework finds neither kANEF key (shared-cache stub)","contested":false}
{"id":"API-108","claim":"IOSurfaceSharedEvent on macOS 27 exposes +initWithMachPort:, +eventPort, -setSignaledValue:, -waitUntilSignaledValue:timeoutMS: and ivar _signaledValue (r^Q shared u64), while the C API surface offers only IOSurfaceSharedEventCreate.","kind":"fact","confidence":"measured","source":"results/EXP-025-ane-gpu-sync/results/surface_probe.txt","source_type":"our-own","retrieved":"2026-10-07","topic":["api","iosurface","shared-events"],"entities":["IOSurfaceSharedEvent"],"contested":false}
{"id":"API-109","claim":"A Path-B .mlmodelc is hand-emittable without Xcode: tmc/apple writes the package in pure Go as four files (model.mil, weights/weight.bin, coremldata.bin, metadata.json plus a .compile_complete marker) and the public +[MLModel compileModelAtURL:error:] compiles a .mlpackage on any Mac.","kind":"open-question","confidence":"documented","source":"https://pkg.go.dev/github.com/tmc/apple/x/coremlcompiler","source_type":"primary","retrieved":"2026-10-07","topic":["api","package-path","toolchain"],"entities":[".mlmodelc","coremldata.bin","compileModelAtURL:"],"caveat":"our reproduction of this route is EXP-025 Lane A, not yet executed","contested":false}
{"id":"API-110","claim":"Public +[MLModel compileModelAtURL:error:] compiles a .mlpackage to .mlmodelc on macOS 27.0.1 with Command Line Tools only — no Xcode, no Go — in under a second, closing the toolchain GAP that blocked EXP-025 phase 1.","kind":"fact","confidence":"measured","source":"results/EXP-025-ane-gpu-sync/results/p2_compile_at_url.txt","source_type":"our-own","retrieved":"2026-10-07","topic":["api","package-path","toolchain"],"entities":["compileModelAtURL:",".mlmodelc","CoreML"],"evidence":"minilm128.mlpackage → /tmp/fresh128.mlmodelc, rc=0, bundle listed in dump","contested":false}
{"id":"API-111","claim":"Current macOS 27 .mlmodelc bundles — both an EXP-003-era cached bundle and a freshly compileModelAtURL-produced one — contain analytics/, coremldata.bin, model.mil and weights/weight.bin, and no model.espresso.net exists in either.","kind":"fact","confidence":"measured","source":"results/EXP-025-ane-gpu-sync/results/p2_bundle_diff.txt","source_type":"our-own","retrieved":"2026-10-07","topic":["api","package-path","bundle-format"],"entities":[".mlmodelc","model.espresso.net","coremldata.bin"],"evidence":"recursive listings of both bundles; espresso.net absent from all current bundle formats","contested":false}
{"id":"API-112","claim":"The legacy _ANEClient Path-B door (modelAtURL:key: then compileModel: or loadModel:) rejects every current-format bundle on 27.0.1 with _ANEEspressoIRTranslator error Cannot load network <bundle>/model.espresso.net — it demands a file generation no current toolchain emits.","kind":"gotcha","confidence":"measured","source":"results/EXP-025-ane-gpu-sync/results/p2_espresso_net_wall.txt","source_type":"our-own","retrieved":"2026-10-07","topic":["api","package-path","gotchas"],"entities":["_ANEClient","_ANEEspressoIRTranslator","model.espresso.net","loadModel:"],"evidence":"identical failure via compileModel: and via loadModel: alone (pkgb_harness SKIPC variant)","contested":false}
{"id":"API-113","claim":"On macOS 27 the live MIL→ANE compilation pipeline is ANECompilerService.xpc: during a public MLModel load it writes model.src and produces model.hwx in a hash-keyed cache that aned reads back.","kind":"fact","confidence":"measured","source":"results/EXP-025-ane-gpu-sync/docs/P2-LANE-A.md","source_type":"our-own","retrieved":"2026-10-07","topic":["api","compiler","architecture"],"entities":["ANECompilerService.xpc","model.hwx","aned"],"evidence":"root fs_usage census (harness/p2_sudo_capture.sh); raw /tmp/p2_sudo_capture.txt root-owned out-of-repo","caveat":"sudo capture is user-run; sudo find on /Library/Caches/com.apple.aned fails 'Operation not permitted' even as root — paths seen via fs_usage only, truncated names not fully resolved (FAILURES F-44)","contested":false}
{"id":"API-114","claim":"macOS 27's Core ML router sent a locally-compiled, ANE-eligible MiniLM to GPU: over a 600-predict public-loop window enginemon recorded GPU Energy 2.35 J (443.2 mW mean) with ANE at 0.0 mW, 0 handlers and 0 B DCS traffic.","kind":"fact","confidence":"measured","source":"results/EXP-025-ane-gpu-sync/results/p2_enginemon_gpu.txt","source_type":"our-own","retrieved":"2026-10-07","topic":["routing","energy","gpu"],"entities":["enginemon","E5","MLE5Engine","MLComputePlan"],"evidence":"enginemon sample window around PROBE_LOOPS=600 of harness/p2_mlmodel_probe.m on Mac17,14","caveat":"one model (minilm128), CLT-pipeline bundle; MLComputePlan-level accept/refuse was not the deciding layer — the E5 executor routed invisibly; RE-STAMPED 2026-10-08 (AN-POS lens validation): the counter that would have caught ANE activity is PMP0/SOC-NI 'SOC-NI9 ANEXL U' (ANE-exclusive, validated 0->14746 on known-ANE program) plus 'SOC-NI8 ANE UP' — both 0 in this window => routing verdict lens-validated true negative","contested":false}
{"id":"API-115","claim":"The shipping E5 prediction path wires work through mach-port shared events and IO-fence toggling: a steady-state dtrace census counts newSharedEventWithMachPort: x131, enableLowLatencyWaitSharedEvent x37, disableIOFencing x131, aneExecutionPriority x78 and e5rtStreamReuseExpectation x130 per predict window.","kind":"fact","confidence":"measured","source":"results/EXP-025-ane-gpu-sync/results/p2_census_e5_selectors.txt","source_type":"our-own","retrieved":"2026-10-07","topic":["routing","shared-events","dispatch"],"entities":["IOSurfaceSharedEvent","MTLSharedEvent","E5","dtrace"],"evidence":"harness/p2_census.d attached to own probe (spawn-then-p, per F-41); 264 MB raw out-of-repo at root","contested":false}
{"id":"API-116","claim":"kANEFDisableIOFencesUseSharedEventsKey and kANEFEnableFWToFWSignal are present in-process in the macOS 27.0.1 AppleNeuralEngine image: an unprivileged dlopen __cstring scan finds 54 kANEF* keys including both targets, plus a block encoding v24@?0@\"IOSurfaceSharedEvent\"8Q16 typed on the bridge class itself.","kind":"fact","confidence":"measured","source":"results/EXP-025-ane-gpu-sync/results/p2_kanef_strings.txt","source_type":"our-own","retrieved":"2026-10-07","topic":["api","shared-events","option-keys"],"entities":["kANEFDisableIOFencesUseSharedEventsKey","kANEFEnableFWToFWSignal","IOSurfaceSharedEvent","_ANEStrings"],"evidence":"harness/p2_kane_scan.c; _ANEStrings exposes no key selectors (harness/p2_kane_strings.m) — keys are image constants","caveat":"presence measured; behavior probes need a loaded ANE program and are deferred to lane A2b","contested":false}
{"id": "API-117", "claim": "ANECompiler.framework dlopens on macOS 27.0.1 (M5 Max) and exports 140 _ANEC* symbols including ANECCompile, ANECCompileJIT, ANECCompileOffline, ANECCompileOnline, ANECCompileWithFunctionCall, per-layer ANEC<Layer>LayerDescInitialize netlist entry points, and ANECGetMPSDialectSupportedVersion; freedomtan's mil_to_hwx and hwx_parsing build CLT-only on 27.0.1 unmodified.", "kind": "fact", "confidence": "measured", "source": "results/EXP-026-ane-kitchen/results/p2b_recon_anecompiler_exports.txt", "source_type": "our-own", "retrieved": "2026-10-07", "topic": ["api", "compiler", "toolchain"], "entities": ["ANECompiler.framework", "ANECCompile", "coreml_to_ane_hwx"], "evidence": "dyld_info -exports dump + dlsym via harness/p2b_fw_probe.m; tools @0da81de built with make", "contested": false}
{"id": "API-118", "claim": "The legacy ANECCompile C door on 27.0.1 rejects all current MIL text with ErrorList=(InvalidMILProgram): 7/7 synthetic conv chains and the real MiniLM coremlc-3600 model.mil, identical across h13g/h16g/h17c targets; renaming the input file to model.src shifts the error to InvalidCompilationParam, and IsMILModel=YES changes nothing — a dialect-level refusal, not op support.", "kind": "gotcha", "confidence": "measured", "source": "results/EXP-026-ane-kitchen/results/p2b_battery_aneccompile.txt", "source_type": "our-own", "retrieved": "2026-10-07", "topic": ["api", "compiler", "gotchas"], "entities": ["ANECCompile", "model.mil", "InvalidMILProgram", "coremltools"], "evidence": "harness/p2b_milgen.py chains + patched mil_to_hwx (P2B_SRCNAME/P2B_ISMIL hooks); p2b_k2_aneccompile_rejections.txt", "contested": false}
{"id": "API-119", "claim": "MilAneflow.framework exposes the modern MIL front-end as a small C API — make_milaneflow_context, milaneflow_try_program_from_string/_from_file, milaneflow_try_function, execute_function, opset_name_list, error-copy pair — and is absent from published ANE reverse-engineering maps; its ABI remained uncracked after in-process probing (all tried signatures returned status 0 with NULL program on both valid and garbage MIL).", "kind": "fact", "confidence": "measured", "source": "results/EXP-026-ane-kitchen/results/p2b_recon_milaneflow_exports.txt", "source_type": "our-own", "retrieved": "2026-10-07", "topic": ["api", "compiler", "open-questions"], "entities": ["MilAneflow.framework", "MIL"], "evidence": "dyld_info -exports + harness/p2b_mila_abi.m / p2b_mila_file.m probe matrices", "caveat": "presence and export table measured; semantics inferred from names only — needs disassembly pass", "contested": false}
{"id": "API-120", "claim": "ANECompilerService and ANELargeModelCompilerService have no MachServices key in their Info.plists and are not registered in the launchd system domain (launchctl print -> Bad request; NSXPCConnection lookup -> error 3); direct-exec of the service binary stays alive as an ordinary user but exits rc=1 under root — the service is spawned on demand by the CoreML client stack, not by launchd.", "kind": "fact", "confidence": "measured", "source": "results/EXP-026-ane-kitchen/results/p2b_k3_xpc_attempts.txt", "source_type": "our-own", "retrieved": "2026-10-07", "topic": ["architecture", "xpc", "compiler"], "entities": ["ANECompilerService.xpc", "ANELargeModelCompilerService.xpc", "launchd"], "evidence": "plutil + /bin/launchctl + harness/p2b_xpc_client error capture; user-run sudo v6 direct-exec log", "contested": false}
{"id": "API-121", "claim": "The public CoreML loader keeps per-identity bookkeeping in ~/Library/Caches/<clientproc>/com.apple.e5rt.e5bundlecache/<OSBUILD>/<IDENT64>/model.milhash; the IDENT64 directory re-keys when weight bytes or MIL text (even buildInfo strings) change. The inferred stale-ANE-program hazard was subsequently REFUTED on the GPU-routed public load path (EXP-027 proof test): an in-place weight-byte edit at the cache-warmed path changed the prediction vector exactly as the same edit at a cold path (output FNV 584eafc1→56a76798, load re-planned 143.7ms vs 30.5ms cached) — bookkeeping-only for this path; full-ANE-AOT bundles untested.", "kind": "gotcha", "confidence": "measured", "source": "results/EXP-026-ane-kitchen/results/p2b_k4_e5bundlecache_identity.txt + results/EXP-027-nax/results/p27_stale_test.txt", "source_type": "our-own", "retrieved": "2026-10-07", "updated": "2026-10-08", "topic": ["caching", "routing", "gotchas"], "entities": ["e5bundlecache", "model.milhash", "ANECompilerService"], "evidence": "8 IDENT dirs with timestamps vs per-mutation load latency table; pgrep polling never observed the service during mutated loads; EXP-027 in-place-edit output-vector equality vs forced-fresh reference", "caveat": "observed for CLT-pipeline .mlmodelc bundles on 27.0.1/M5Max via MLModel load path; refutation measured on the GPU-routed MiniLM bundle only", "contested": false}
{"id": "API-122", "claim": "Espresso is a dead package-format, not dead input: public compileModelAtURL: of a legacy .mlmodel (coremltools-4 era MobileNetV2) on 27.0.1 still emits the full espresso trio model.espresso.net/.shape/.weights, and the EXP-025 pathb harness on that bundle fails two stages deeper than the translator — mapIOSurfacesWithModel: 0x1D (surface geometry) — meaning compile and load of a hand-inspected espresso bundle succeed on 27.", "kind": "fact", "confidence": "measured", "source": "results/EXP-026-ane-kitchen/results/p2b_k5_espresso_door.txt", "source_type": "our-own", "retrieved": "2026-10-07", "topic": ["api", "espresso", "package-path"], "entities": ["compileModelAtURL:", "model.espresso.net", "mapIOSurfacesWithModel:", "MobileNetV2"], "evidence": "harness/p2b_compile.m output + pkgb_harness PATHB_DIR=/tmp/mnv2.mlmodelc run", "contested": false}
{"id": "API-123", "claim": "A .mlmodelc weights/weight.bin opens with a ~1 KiB manifest (leading uint32s 101/2 = tensor count/version; at 0x40 magic 0xDEADBEEF followed by per-tensor byte sizes, e.g. 23440896 = 30522x384x2 for a MiniLM embedding table): overwriting the manifest head with tensor values fails MLModel init with Failed to build the model execution plan ... error code: -5, while fp16 edits at offset 0x400+ load fine and change prediction output.", "kind": "gotcha", "confidence": "measured", "source": "results/EXP-027-nax/results/p27_stale_test.txt", "source_type": "our-own", "retrieved": "2026-10-08", "topic": ["caching", "gotchas", "tooling"], "entities": ["weight.bin", "MLModel", "e5bundlecache"], "evidence": "differential 64-byte fp16 edits at offsets 0x80..0x100000 with per-process output FNV hashes; head-clobber produced error -5, data-region edits returned changed vectors", "caveat": "measured on one CLT-pipeline MiniLM-128 bundle on 27.0.1/M5Max; manifest field meanings partly inferred", "contested": false}
{"id": "API-124", "claim": "MilAneflow.framework's C ABI (macOS 27.0.1/M5 Max): make_milaneflow_context(void) returns a 16B shared_ptr ctx; milaneflow_try_program_from_string/_from_file return {program, errorInfo} in x0/x1; error_message_size/copy take the errorInfo (libc++ SSO strings at +0x00/+0x18), NOT the ctx; arg3 is modelPath resolving @model_path BLOBFILE refs; function_name_list returns {count, buffer}; try_function(prog, unused, funcName, opsetName) enforces three gates (function exists / declares opset tag / tag in AneFlow family). All 10/10 K2-rejected battery MILs parse clean through this front-end — InvalidMILProgram is ANECCompile-specific.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-027-nax/results/p27_mila_abi2_findings.txt", "source_type": "our-own", "retrieved": "2026-10-08", "topic": ["private-api", "mil", "compilation"], "entities": ["MilAneflow.framework", "milaneflow_try_program_from_string", "ANECCompile"], "evidence": "dyld_info -disassemble of shared-cache image mapped ABI; differential probes (valid vs garbage MIL, stage-differentiated errors); disasm dump raw/", "caveat": "reverse-engineered from disassembly + probes on one OS build; offsets/register conventions unverified against future betas", "contested": false}
{"id": "API-125", "claim": "The AneFlow opset family on 27.0.1 is aneflowh2020/aneflowh2021/aneflowh2022 (from LookupOpsetString byte-compares), and the MIL grammar accepts func-main tags ios15 through ios19 only — no CoreML-produced MIL text (which carries its own dialect tags) passes try_function gate 2, corroborating 27.0.1 GPU routing of CoreML models from a second, independent subsystem.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-027-nax/results/p27_mila_abi2_findings.txt", "source_type": "our-own", "retrieved": "2026-10-08", "topic": ["private-api", "routing", "mil"], "entities": ["MilAneflow.framework", "aneflowh2020", "try_function"], "evidence": "3-gate error ladder over 10 bundles + tag whitelist from grammar parser messages (p27_mila_battery.txt)", "caveat": "implies an unexplored producer exists that tags functions aneflowh*; not found via CoreML paths tried", "contested": false}
{"id": "API-126", "claim": "Path-B espresso bundle evaluation on 27.0.1 works end-to-end without shared events: mapIOSurfacesWithModel: succeeds when IOSurfaces are sized to the model's BatchStride (301056 B input / 64064 B output fp16 for 1x3x224x224 MobileNetV2 — the EXP-026 0x1D was size mismatch, not format), and doEvaluateDirect on _ANEProgramForEvaluation then runs a non-chain predict at median ~0.39-0.43 ms; attaching non-empty waitEvents (_ANESharedEvents) SIGSEGVs the same first eval at processRequest...+1524 on ANEServicesThread (F-40 frame), with kANEFDisableIOFencesUseSharedEvents/kANEFEnableFWToFWSignal accepted but consuming nothing in-process.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-027-nax/results/p27_es_findings.txt", "source_type": "our-own", "retrieved": "2026-10-08", "topic": ["private-api", "ane", "shared-events"], "entities": ["_ANEProgramForEvaluation", "mapIOSurfacesWithModel", "doEvaluateDirect", "kANEFDisableIOFencesUseSharedEvents"], "evidence": "p27_es_harness.m run log: 9/9 kANEF probes, 7 SIGSEGV-exclusion variants measured (compile/ev-only/alt-selector/eventType 0,1,3/-sharedEvent provider/empty reject)", "caveat": "one espresso bundle (coremltools-4 MobileNetV2); dims per-bundle via LiveInputList plain dict", "contested": false}
{"id": "API-127", "claim": "ANE-exclusive user-mode IOReport lenses exist on M5 Max: PMP0/SOC-NI 'Util BW'->'SOC-NI9 ANEXL U' (0->14746 for a full-ANE-region program, 0 during GPU-routed control) and 'SOC-NI8 ANE UP' (9->13766); PMP0 DCS/AF BW ANE L0/L1 lanes also rise (0->28141) but move 21101 in the GPU window too (non-exclusive, flagged). UT perf-state PS13 stays 0 during full-ANE execution — PS13 (NAX/GPU) and ANEXL (ANE) are disjoint lenses; ANE zeros recorded in EXP-025/K6b routing runs are therefore true negatives, not a blind lens.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-027-nax/results/p27_anpos_counters.txt", "source_type": "our-own", "retrieved": "2026-10-08", "topic": ["attribution", "counters", "ane"], "entities": ["SOC-NI9 ANEXL U", "SOC-NI8 ANE UP", "enginemon", "IOReport"], "evidence": "lane-exclusive windows idle/ANE/GPU/idle over EXP-013 reranker h17g ANE_region bundle (JIT 78ms/pair, GPU control 32.6ms/pair); 4 jsonl windows archived", "caveat": "single full-ANE-region program; ANEXL semantics inferred from known-ANE exclusivity", "contested": false}
{"id": "API-128", "claim": "M5 Max exposes ZERO TENSOR/NAX-named IOReport channels (4606-row unfiltered --list enumeration); matmul2d work is visible only through generic GPU lenses — GPU Energy nJ and UT Perf_State_13 engagement counts — and calibration shows PS13 fires identically under plain MSL simdgroup_matrix dispatch (idle 0 -> 125798/tick), so PS13 means saturated top-perf-state GPU compute, NOT matmul2d specifically; enginemon JSON subscriptions cap at 4096 channels and --unfiltered silently drops the UT set.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-027-nax/results/p27_nxd_nax_lenses.txt", "source_type": "our-own", "retrieved": "2026-10-08", "topic": ["attribution", "counters", "nax"], "entities": ["IOReport", "AGX.Count_UT_Engagement_Perf_State_13", "enginemon", "matmul2d"], "evidence": "idle-vs-30s-load diff over 4096-channel windows + 1.32M-dispatch MSL load (p27_nxd_*.jsonl, raws gzipped)", "caveat": "calibration child was MSL (coreai matmul2d window blocked by co-tenant surface saturation that day); PS13 response to matmul2d itself shown in NX-C", "contested": false}
{"id": "API-129", "claim": "GPU routing on 27.0.1 is not family-specific: a 400-predict MobileNetV2 (conv-family) public loop moved GPU Energy +246.8 mJ with AGX UT engagement while every ANE counter stayed 0 — handler interrupts 0, DCS bytes 0, GFX-ANE lane bytes 0; lens-validated 2026-10-08 (EXP-027 AN-POS): the ANE-exclusive counters that would have caught ANE activity, PMP0/SOC-NI 'SOC-NI9 ANEXL U' and 'SOC-NI8 ANE UP', were 0 in the window, so the zeros are true negatives, not a blind lens (validation status: validated on EXP-013 full-ANE-region program, disjoint from GPU PS13).", "kind": "measurement", "confidence": "measured", "source": "results/EXP-026-ane-kitchen/results/p2b_k6b_enginemon_mobilenet.txt + results/EXP-027-nax/results/p27_anpos_counters.txt", "source_type": "our-own", "retrieved": "2026-10-07", "updated": "2026-10-08", "topic": ["routing", "counters", "gpu"], "entities": ["MobileNetV2", "enginemon", "SOC-NI9 ANEXL U", "SOC-NI8 ANE UP"], "evidence": "400-predict loop window vs idle baselines; AN-POS lane-exclusive validation of both ANE counters", "caveat": "two data points total with MiniLM (API-114); conv+transformer coverage only, both public CoreML path", "contested": false}
{"id": "API-130", "claim": "On 27.0.1 the JIT-route model.src is not a text file in the ANECompilerService sandbox: compilation is in-process and the full lineage persists user-readable under ~/Library/Caches/coreai-cache/<OSBUILD|pyver>/<proc>/<IDENT64>/<plan-hash64>/ — manifest.plist (complete compilationDescriptor JSON, deviceDescriptor [0,40,h17c], inputShapes), original_model_N.mpsgraph = the model source as MLIR bytecode (magic ML-EF-R, producer MLIR22.0.0git, bytecode v6, private mps dialect), specialized_model_N.mpsgraph (placement with *_ANE_region_*/_GPU_region_* symbols, ane_family A18, ANE dtype whitelist fp16/f8E4M3/si8/ui8/si16/ui16), binary_0.llir.bundle with per-region h17c LLIR bitcode (ANECompiler 10.26.4, LLIRVersion 0.1b, anehlo/raster/llir dialects, fused anec.linear/anec.swish kernels), and freedomtan-parseable binary_0.hwx ANE task binaries (LE magic 0xBEEFFACE, CPU 0x0080 subtype 0x9, InDim/OutDim/DMA/L2/coeff fields).", "kind": "measurement", "confidence": "measured", "source": "results/EXP-026-ane-kitchen/results/p2b_model_src_inventory.txt + harness/p2b_mlir_bc_strings.py + raw/p2b_model_src/", "source_type": "our-own", "retrieved": "2026-10-08", "updated": "2026-10-08", "topic": ["compiler", "cache", "mlir", "model-src"], "entities": ["coreai-cache", "MPSGraph", "ANECompiler", "hwx", "mlir-opt"], "evidence": "census of ~3.5GB cache 2026-10-08; string-dictionary decodes of granite original/specialized/region0 LLIR; hwx_parsing decode of na_tiles binary_0.hwx; stock mlir-opt parses container then stops only at private-dialect instantiation", "caveat": "op order/operand wiring needs a DialectPlugin stub for full generic text; bnns.ir delegate (Swift runner route) has a different container, not covered", "contested": false}
{"id": "API-131", "claim": "ANE compilation is confirmed in-process for the CoreAI/MPSGraph JIT route: v8 sudo watcher (per-poll aned-sandbox directory watch, both trigger lanes verified live — JIT median 77.2ms n=235 and mutated-bundle reload rc=0) recorded ZERO aned process or sandbox-file activity; and the cached plans measure hybrid placement: granite embedding w8 JIT = 13 ANE regions (all carrying fused anec.linear neconv kernels, 12/13 also anec.swish) + 14 GPU region symbols with GPU adapter present NO, while the EXP-013 reranker JIT on 27.0.1 produced specialized_model with useANELLIR false and no ANE regions; bench/na_tiles.py coreai plans each carry a decoded hwx ANE task (InDim W=32 H=1 C=64 float16, ActiveNE=4) meaning matmul-tile fragments also reach the ANE compiler on this route.", "kind": "measurement", "confidence": "measured", "source": "results/EXP-026-ane-kitchen/results/p2b_model_src_{inventory,region_llir,hwx,diff}.txt", "source_type": "our-own", "retrieved": "2026-10-08", "updated": "2026-10-08", "topic": ["routing", "compiler", "cache", "placement"], "entities": ["aned", "granite", "RerankerANE", "na_tiles", "h17c"], "evidence": "v8 watcher log + coreai-cache plan census (26A434/python granite entry, 26A434/org.python.python reranker entry, 3.12.15 na_tiles entries)", "caveat": "hybrid region counts are from compiler artifacts (placement symbols), not runtime counter attribution; na_tiles ANE-task presence does not by itself say which regions executed there at runtime", "contested": false}
```
