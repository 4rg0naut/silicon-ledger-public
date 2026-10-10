# ANE sync/event symbol inventory — macOS 27.0.1 (26A434), Mac17,14 (M5 Max)

All signatures from runtime ObjC introspection (`harness/ane_class_dump.m`, `harness/ane_surface_probe.m`),
run 2026-10-07. Raw: `results/class_dump.txt`, `results/surface_probe.txt`.
Framework binary is in the dyld shared cache (on-disk bundle is a stub — `nm -gU` on it yields 0 symbols).
Method polarity (`-`/`+`) taken from class vs metaclass method lists (an earlier dump had wrong polarity — corrected).

## Verdict-relevant classes (pattern `_ANE(Shared|Signal|Wait|Fence|Sync|Event)`)

Exactly **3** classes match, all in `/System/Library/PrivateFrameworks/AppleNeuralEngine.framework`
(scan of 10,398 classes; `results/class_dump.txt`): `_ANESharedEvents`, `_ANESharedSignalEvent`,
`_ANESharedWaitEvent`. **All three exist on this OS.** No `_ANEFence*` / `_ANESync*` class exists.
(`_ANEPerformanceStatsIOSurface` exists but is perf-stats, not sync.)

### _ANESharedWaitEvent : NSObject
```
- initWithValue:(u64) sharedEvent:(IOSurfaceSharedEvent*) eventType:(u64)      @40@0:8Q16@24Q32
- sharedEvent   -> IOSurfaceSharedEvent*    (ivar _sharedEvent @"IOSurfaceSharedEvent")
- value         -> u64
- eventType     -> u64   (semantics unknown; not documented anywhere public)
```

### _ANESharedSignalEvent : NSObject <NSSecureCoding>
```
- initWithValue:(u64) symbolIndex:(u32) eventType:(i64) sharedEvent:(IOSurfaceSharedEvent*) agentMask:(u64)   @52@0:8Q16I24q28@36Q44
- waitEvent     -> _ANESharedWaitEvent*
- agentMask     -> u64   (unknown; plausibly per-engine-agent bits, INFERRED)
- encodeWithCoder:/initWithCoder:   ← designed for XPC transport to aned
```

### _ANESharedEvents : NSObject
```
- initWithSignalEvents:(NSArray*)_ANESharedSignalEvent waitEvents:(NSArray*)_ANESharedWaitEvent
```

## Consumers (how the dispatch path takes them)

From `results/surface_probe.txt` (consumer scan over all AppleNeuralEngine classes):
```
_ANERequest          -setSharedEvents: / -sharedEvents
_ANERequest          -initWithInputs:...:procedureIndex:sharedEvents:transactionHandle:   (9-arg init)
_ANERequest          +requestWithInputs:...:procedureIndex:  (7-arg factory; sharedEvents nil)
_ANESharedSignalEvent-sharedEvent / -waitEvent
_ANESharedWaitEvent  -initWithValue:sharedEvent:eventType:
```

## The Metal bridge (C2 answer)

**There is no `@"MTLSharedEvent"` or `@"MTLSharedEventHandle"` in any ANE type encoding.**
The bridging type is **`IOSurfaceSharedEvent`** (`/System/Library/Frameworks/IOSurface.framework`,
verified `class_getImageName` in `results/surface_probe.txt`):

```
IOSurfaceSharedEvent : NSObject            (runtime-only: NOT in the macOS 27 SDK headers)
- initWithMachPort:(unsigned)              @20@0:8I16
- eventPort         -> unsigned            mach port name
- signaledValue / setSignaledValue:        u64 counter
- waitUntilSignaledValue:timeoutMS: -> BOOL
- notifyListener:atValue:block:
- supportsRollback -> BOOL
- ivar _signaledValue: r^Q                 (shared-memory u64 reference)
C API: IOSurfaceSharedEventCreate PRESENT (dlsym); EncodeWait/EncodeSignal absent.
```

`MTLSharedEventHandle` (Metal.framework):
```
- initWithSharedEvent:(MTLSharedEvent*)
- eventPort      -> unsigned               ← same unsigned-port surface
- ivar _priv: ^{MTLSharedEventHandlePrivate=I@Q}   (I = mach port)
```

Linkage evidence (`dyld_info -linked_dylibs -all_dyld_cache`, full dump
`/tmp/dylibs.txt` on the submitting machine): `AppleNeuralEngine` links **IOSurface + IOKit,
NOT Metal**; `/usr/libexec/aned` (`otool -L`) likewise links IOSurface + IOKit, not Metal.
The common substrate is IOSurface, not Metal — but the mach-port pair makes the two event
objects two wrappers over one kernel primitive, confirmed by round-trip tests
(`results/porttest.txt`):

```
MTLSharedEvent --eventPort--> IOSurfaceSharedEvent initWithMachPort:
T1 CPU signal MTLSharedEvent   -> wrapper wait observed   PASS
T2 GPU encodeSignalEvent       -> wrapper wait observed   PASS  (hardware write path)
T3 wrapper setSignaledValue    -> MTLSharedEvent observed PASS
```

## Fragility note

Every row above observed only on macOS 27.0.1 build 26A434 / M5 Max (Mac17,14).
Private API; no ABI promise. `IOSurfaceSharedEvent` absent from SDK headers = no compile-time API.
