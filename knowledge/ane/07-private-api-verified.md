# Private ANE API — verified on this machine (macOS 27.0, M4)

**Why this file exists.** `02-private-api.md` documents the private API from other people's repos,
built on other macOS versions. Private APIs move. This is what `AppleNeuralEngine.framework`
*actually* exposes here, read from the runtime rather than from documentation.

**Method.** `bench/ane-probe.m` — dlopens the framework, then enumerates classes with
`objc_copyClassList` and methods with `class_copyMethodList`. No weights, no compilation, no model.
Run: `clang -O2 -o bench/ane-probe bench/ane-probe.m -framework Foundation && ./bench/ane-probe`

---

## Device, queried live

| selector | returns | type |
| --- | --- | --- |
| `+numANECores` | **16** | `I` (uint32) |
| `+numANEs` | **1** | `I` |
| `+aneArchitectureType` | **`h16g`** | object |
| `+aneSubType` | `h16` | object |
| `+productName` | `macOS` | object |
| `+isVirtualMachine` | `NO` | `B` |
| `+aneBoardType` | 256 | `q` (int64) |

**`h16g` is the same string our AOT builds target** (`coreai-build compile --architecture h16g`), so
the private API and the official toolchain agree on what this silicon is.

**Method note that cost a segfault:** these return *scalars*, not objects. Casting the result to `id`
and sending `-description` dereferences the value as a pointer — `numANECores` = 16 faults at address
`0x10`. Check the type encoding before messaging anything.

---

## Class existence — 39 `_ANE` classes registered

**Our 19 documented names: 15 present, 4 absent.**

| absent | our KB had said |
| --- | --- |
| `_ANECompiler` | *"cited as a class by Orion and maderix prose but exists in no class dump... the name is really the log/error prefix `_ANECompiler : ANECCompile() FAILED`"* |
| `_ANEMemoryModel` | *"has no evidence of existing at all"* |
| `_ANEProgram` | "seen in some dumps" |
| `_ANEModelCache` | "seen in some dumps" |

**Both of the KB's corrections are confirmed on macOS 27.** The four "seen in some dumps" names do not
exist here.

### The full list

```
_ANEClient              _ANEInMemoryModel        _ANEInMemoryModelDescriptor
_ANEModel               _ANEProgramForEvaluation _ANERequest
_ANEChainingRequest     _ANEIOSurfaceObject      _ANEIOSurfaceOutputSets
_ANEDeviceInfo          _ANEDeviceController     _ANEQoSMapper
_ANEStrings             _ANEErrors               _ANESharedEvents
_ANESharedWaitEvent     _ANESharedSignalEvent    _ANEDaemonConnection
_ANEVirtualClient       _ANECloneHelper          _ANEBuffer
_ANESandboxingHelper    _ANEInputBuffersReady    _ANEPerformanceStats
_ANEProgramIOSurfacesMapper  _ANETensorDebugHelper  _ANEIntermediateTensor
_ANECompileFlavorPolicy _ANEDebugUtils           _ANEHashEncoding
_ANEProgramProcedurePriv _ANEOutputSetEnqueue     _ANEPerformanceStatsIOSurface
_ANEModelInstanceParameters  _ANEWeight          _ANEProcedureData
_ANEDataReporter        _ANEModelToken           _ANELog
```

---

## What is new to us — capabilities our KB did not have

### 1. Real-time tasks

```
-[_ANEClient beginRealTimeTask]
-[_ANEClient endRealTimeTask]
-[_ANEClient loadRealTimeModel:options:qos:error:]
-[_ANEClient unloadRealTimeModel:options:qos:error:]
-[_ANEClient evaluateRealTimeWithModel:options:request:error:]
```

A whole latency-mode API — load and evaluate under a real-time constraint. This is a setting the
official Core AI path does not expose at all.

### 2. Mutable weights — this settles a contested question

Our KB recorded the weight-patching question as **contested**: Orion reported patching weights after
compile (4200 ms → 494 ms), libane reported *zero* effect. The API surface answers it:

```
-[_ANEClient mapMutableWeightsForModel:andProcedure:mappedWeightsBuffer:size:error:]
-[_ANEClient unmapMutableWeightsForModel:andProcedure:]
-[_ANEClient syncMutableWeightsForModel:andProcedure:fromOffset:withSize:error:]
-[_ANEProgramForEvaluation mapMutableWeightsBufferDirectForProcedure:bufferID:buffer:size:error:]
-[_ANEProgramForEvaluation unmapMutableWeightsBufferDirectForProcedure:bufferID:]
```

**Apple ships a full mutable-weights path**, including a `syncMutableWeights...fromOffset:withSize:`
for partial updates. So weight patching is supported — libane's null result was likely a
methodology problem, not an absent capability. Worth re-testing.

### 3. Hash-tracked model cache

```
-[_ANEClient compiledModelExistsMatchingHash:]
-[_ANEClient purgeCompiledModelMatchingHash:]
-[_ANEClient updateCachedModelLocationForModelTrackedByHash:toAppGroup:error:]
-[_ANEClient updateSourcePathForModelTrackedByHash:to:error:]
-[_ANEClient updatePurgeabilityLevelForModelTrackedByHash:to:]
-[_ANEClient compiledModelExistsInCacheFor:limitToCurrentProcess:]
```

Compiled models are cached and tracked **by hash**, with an app-group location and a purgeability
level. Relevant to the ~119-compile-per-process limit: a cache keyed by hash is how you avoid
recompiling.

### 4. Model instance parameters

```
-[_ANEClient loadModelNewInstance:options:modelInstParams:qos:error:]
-[_ANEClient doLoadModelNewInstance:options:modelInstParams:qos:error:]
_ANEModelInstanceParameters
```

One compiled model, multiple loaded instances with per-instance parameters.

### 5. Compile flavour policy

`_ANECompileFlavorPolicy` — a class we had no record of. Compilation is not one thing.

### 6. `+sharedPrivateConnection`

Alongside `+sharedConnection`. A second connection class, distinct from the shared one.

---

## Signatures, as the runtime reports them

Encoding legend: `@` object · `Q` uint64 · `I` uint32 · `q` int64 · `c` char · `B` BOOL · `^@` NSError**

### `_ANEInMemoryModel` — the Path A lifecycle

```
+ inMemoryModelWithDescriptor:                          @24@0:8@16
- initWithDesctiptor:                                   @24@0:8@16     ← Apple's own typo, confirmed
- compileWithQoS:options:error:                         B36@0:8I16@20^@28
- loadWithQoS:options:error:                            B36@0:8I16@20^@28
- evaluateWithQoS:options:request:error:                B44@0:8I16@20@28^@36
- unloadWithQoS:error:                                  B28@0:8I16^@20
- hexStringIdentifier                                   @16@0:8
- mapIOSurfacesWithRequest:cacheInference:error:        B36@0:8@16B24^@28
- unmapIOSurfacesWithRequest:                           v24@0:8@16
- compiledModelExists                                   B16@0:8
- compilerOptionsWithOptions:isCompiledModelCached:     @28@0:8@16B24
- queueDepth                                            c16@0:8        ← int8; the KB's "unexplained 127" is a signed char
- state / string_id / programHandle / intermediateBufferHandle   Q16@0:8
```

### `_ANEClient` — the Path B lifecycle

```
+ sharedConnection / + sharedPrivateConnection
- initWithRestrictedAccessAllowed:                      @20@0:8B16
- compileModel:options:qos:error:                       B44@0:8@16@24I32^@36
- loadModel:options:qos:error:                          B44@0:8@16@24I32^@36
- doEvaluateDirectWithModel:options:request:qos:error:  B52@0:8@16@24@32I40^@44   ← bypasses the daemon
- evaluateWithModel:options:request:qos:error:          B52@0:8@16@24@32I40^@44
- prepareChainingWithModel:options:chainingReq:qos:error:  B52@0:8@16@24@32I40^@44
- buffersReadyWithModel:inputBuffers:options:qos:error:    B52@0:8@16@24@32I40^@44
- enqueueSetsWithModel:outputSet:options:qos:error:        B52@0:8@16@24@32I40^@44
- sessionHintWithModel:hint:options:report:error:          B56@0:8@16@24@32@40^@48
```

### `_ANEProgramForEvaluation` — the fastest dispatch

```
+ programWithController:intermediateBufferHandle:queueDepth:
+ programWithHandle:intermediateBufferHandle:queueDepth:
- processRequest:model:qos:qIndex:modelStringID:options:returnValue:error:   B76@0:8@16@24I32Q36Q44@52^I60^@68
- processInputBuffers:model:options:error:
- processOutputSet:model:options:error:
```

### `_ANEIOSurfaceOutputSets` — the error-15 fix, confirmed

```
+ objectWithstatsSurRef:outputBuffer:      ← the correct factory
- initWithstatsSurRef:outputBuffer:
- statsSurRef   ^{__IOSurface=}
- outputBuffer  @
+ supportsSecureCoding
```

**`objectWithstatsSurRef:outputBuffer:` exists and is the only factory.** Our KB's record — that error
15 came from using the wrong `_ANEIOSurfaceOutputSets` API — is confirmed by the surface itself.

---

## What this changes for the plan

**The direct path offers control the official path does not:**

| capability | private | Core AI |
| --- | --- | --- |
| real-time task mode | ✓ | ✗ |
| mutable weights, partial sync | ✓ | ✗ |
| compile flavour policy | ✓ | ✗ |
| model instance parameters | ✓ | ✗ |
| hash-keyed compile cache control | ✓ | ✗ |
| `doEvaluateDirect` (no daemon round trip) | ✓ | ✗ |
| explicit queue depth / QoS index | ✓ | ✗ |
| dispatch a **specific procedure** by index | ✓ | limited |

**And the reason to want granularity is concrete.** The 1 MiB DMA erratum is fixed by *splitting a
kernel-DMA task in two*. That is a change to the compiled program, which the official path does not
let us make. **On the direct path we control the program.**

**Next steps, in order:**

1. Load a small MIL program through Path A and time it against our Core AI path on the same graph —
   the `doEvaluateDirectWithModel:` claim of 10% and `processRequest:` claim of 13% are testable here.
2. Exercise `syncMutableWeights...fromOffset:withSize:` to settle the weight-patching dispute.
3. Build a graph whose per-core transfer is an exact multiple of 1 MiB, then split it — the DMA
   erratum test, which needs the control this path provides.

**Caveat, unchanged:** all of this is private and undocumented. Apple can break it in any OS update.
Research-grade.
