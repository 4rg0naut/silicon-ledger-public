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
| `_ANEChainingRequest`, `_ANEBuffer`, `_ANEIOSurfaceOutputSets`, `_ANEInputBuffersReady`, `_ANEOutputSetEnqueue`, `_ANESharedEvents`, `_ANESharedSignalEvent`, `_ANESharedWaitEvent` | Firmware-level pipeline chaining and cross-engine signalling. Partly reachable; see §3.10 and §6. | ane-infer (explored), libane (explored, blocked) |
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
8. **`_ANESharedEvents` on the MIL path.** libane reports an unconditional `EXC_BAD_ACCESS` at
   `address 0x10` (a C++ vtable call on a nil pointer) inside
   `-[_ANEProgramForEvaluation processRequest:...]_block_invoke`, with a precise crash-condition matrix.
   That is a good bug report and a real limitation, not a documented behaviour.
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

External, fetched and read on 2026-09-23:

* https://github.com/nst/iOS-Runtime-Headers/tree/master/PrivateFrameworks/AppleNeuralEngine.framework — `_ANEClient.h`, `_ANEModel.h`, `_ANERequest.h`, `_ANEDaemonConnection.h`, `_ANEIOSurfaceObject.h`, `_ANEProgramForEvaluation.h`, `_ANEDeviceController.h`, `_ANEDeviceInfo.h`, `_ANEStrings.h`, `_ANEErrors.h`, `_ANEQoSMapper.h`, `_ANECloneHelper.h`, `_ANEHashEncoding.h`, `_ANELog.h`, `_ANEDataReporter.h` (old iOS era; repo archived read-only 2026-09-08)
* https://github.com/maderix/ANE — `bridge/ane_bridge.m`, `bridge/ane_bridge.h`, `bridge/Makefile`, `api_exploration.m`, `training/ane_runtime.h`, `training/test_weight_patch.m`, `training/test_weight_reload.m`, `README.md`
* https://github.com/johnmai-dev/ANE-LM — `core/ane_runtime.cpp`, `core/ane_runtime.h`
* https://github.com/AmiraniLabs/libane — `src/runtime/ane_runtime.mm`, `docs/ane-runtime-boundary.md`, `README.md`, `include/libane.h`, `bindings/python/ane.pyi`
* https://github.com/thebasedcapital/ane-infer — `crates/ane-bridge/objc/ane_runtime.m`, `crates/ane-bridge/build.rs`, `crates/ane-bridge/src/lib.rs`, `docs/ane-internals.md`
* https://github.com/tinygrad/tinygrad/tree/d0e752003da3fc023fa85094d7f5b65b47dd5091/extra/accel/ane — `README.md`, `lib/ane.mm`, `lib/ane.py`, `3_run/entitlements.xml`
* https://github.com/tmc/apple/tree/main/private/appleneuralengine — generated bindings, one `*_name_.gen.go` per class (current-macOS class and method inventory)
* https://arxiv.org/abs/2603.06728 — "Orion: Characterizing and Programming Apple's Neural Engine for LLM Training and Inference" (private-API table, delta compilation, 20-constraint catalog)

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
```