# VERDICT — ANE↔GPU shared-event sync primitive

**Machine:** Mac17,14 (M5 Max) · **OS:** macOS 27.0.1 (26A434) · **Date:** 2026-10-07
Every claim below cites a dump line, trace line, crash frame, or harness output in
this pack's `results/` (or `docs/`). No symbol appears here that is absent from
those files.

## Verdict: (a) — a viable hardware sync path EXISTS, with two caveats

A GPU→ANE (and ANE→GPU) hardware signalling path exists on this machine:
`MTLSharedEvent` and the ANE's private event classes are **two Objective-C wrappers over
the same kernel shared-event port primitive** (`IOSurfaceSharedEvent`). A Metal encoder
can signal the counter that an ANE request waits on — hardware write, no CPU round-trip —
**provably across the wrapper boundary** (porttest T2, below). Caveats: (1) on the
in-memory-MIL dispatch path (Path A) the ANE framework **crashes** when the events object
is attached, i.e. consumption is firmware-gated to the Path-B `intermediateBufferHandle`
flow; (2) Path B could not be exercised end-to-end on this box because the system
Espresso compiler rejects every model source available here (no full Xcode). The
*primitive* is verified; the *dispatch integration* is verified-only-up-to-the-daemon.

## Evidence chain

### E1. The three target classes exist, exactly as named
Runtime scan of 10,398 classes, image-filtered to AppleNeuralEngine.framework —
exactly 3 matches (`results/class_dump.txt`):

```
# scanned 10398 classes, 3 matched image+pattern
=== _ANESharedWaitEvent ... === _ANESharedSignalEvent ... === _ANESharedEvents
```

### E2. The Metal bridge type is `IOSurfaceSharedEvent` — quoted ivar/property encodings
From `results/class_dump.txt`:

```
_ANESharedWaitEvent  ivar  _sharedEvent   @"IOSurfaceSharedEvent"
                     prop  sharedEvent    T@"IOSurfaceSharedEvent",R,N,V_sharedEvent
_ANESharedSignalEvent ivar _sharedEvent   @"IOSurfaceSharedEvent"
                     prop  sharedEvent    T@"IOSurfaceSharedEvent",R,N,V_sharedEvent
_ANESharedEvents     ivars _signalEvents/_waitEvents  @"NSArray"
```

No method or ivar anywhere in the three classes mentions `MTLSharedEvent` or Metal
(C2 consumer scan, `results/surface_probe.txt`: 15 hits, all `IOSurfaceSharedEvent` /
container types). AppleNeuralEngine and aned link IOSurface + IOKit but **not Metal**
(`otool -L` / `dyld_info -linked_dylibs`, recorded in docs/SYMBOLS.md).

### E3. Both wrappers expose the same kernel handle: a mach port
`results/surface_probe.txt`:

```
IOSurfaceSharedEvent  (image: .../IOSurface.framework/.../IOSurface)
  + initWithMachPort:      @20@0:8I16
  + eventPort              I16@0:8
  ivar _signaledValue      r^Q          (shared-memory u64 counter)
  + waitUntilSignaledValue:timeoutMS:   B32@0:8Q16Q24
  + setSignaledValue:      v24@0:8Q16

MTLSharedEventHandle  (image: .../Metal.framework/.../Metal)
  + eventPort              I16@0:8
  ivar _priv               ^{MTLSharedEventHandlePrivate=I@Q}   (I = mach port)
```

`IOSurfaceSharedEvent` is runtime-only — absent from the macOS 27 SDK headers; discovered
via in-process class probe, not invented. The C-API sweep in the same file shows only
`IOSurfaceSharedEventCreate` PRESENT (all Encode*/SignaledValue* C names absent).

### E4. Hardware write crosses the wrapper boundary (no CPU in the loop)
`results/porttest.txt` — one process holds an `MTLSharedEvent`; wraps its
`eventPort` into an `IOSurfaceSharedEvent`; a **Metal compute encoder** signals:

```
porttest: MTLSharedEvent value=0 handle=ok eventPort=12299
T1 CPU-signal -> wrapper-wait : PASS
T2 GPU-encodeSignal -> wrapper-wait : PASS (gpu commit->wait 62us)
T3 wrapper-signal -> MTLSharedEvent : PASS (value=3)
```

T2 is the load-bearing result: `encodeSignalEvent:setValue:` (GPU-side hardware counter
write) unblocked `waitUntilSignaledValue:` on the IOSurface-side wrapper in ~62µs — the
kernel event object is shared between both wrappers, bidirectionally (T3).

### E5. The ANE dispatch API consumes the events object
`results/surface_probe.txt` (consumer scan, quoted):

```
_ANERequest      -setSharedEvents:                          v24@0:8@16
_ANERequest      -initWithInputs:...:perfStats:procedureIndex:sharedEvents:transactionHandle:  @88...
_ANEChainingRequest -initWithInputs:...:signalEvents:transactionHandle:fwEnqueueDelay:memoryPoolId: @88...
```

### E6. How completion is actually delivered (daemon + client forensics)
- aned debug log (2,766 lines, `results/aned_logshow_eval.log.gz`): full
  `ANEDeviceOpen`/`ANE_ProgramCreate, input buffer count: 1, output buffer count: 1`/
  `ANEDeviceClose` lifecycle; **zero** lines containing signal/wait/event/fence —
  completion is not named on the daemon side (docs/TRACE.md §"What aned logs").
- Client side, crash-report stack (docs/TRACE.md §"Client-side completion path"):
  `ANERequestReceiver::FrameDone` ← `IODispatchCalloutFromCFMessage` ←
  `__CFMachPortPerform` → run loop. The *callback* channel is an IOKit mach-port
  message; Metal never appears in any frame. Metal's role is purely the counter write.

### E7. Dispatch path consults shared events per eval (primary-channel dtrace)
`results/dtrace_ane_methods.txt.gz` (pid-provider `-[_ANE*]` entries on our own harness):

```
-[_ANEInMemoryModel evaluateWithQoS:options:request:error:]              1686
-[_ANEProgramForEvaluation processRequest:model:qos:qIndex:modelStringID:options:returnValue:error:]  1686
-[_ANERequest sharedEvents]                                              6744   (= 4 per eval)
+[_ANEClient sharedConnection] / compileModel / loadModel vocabulary: 151 distinct methods
```

The framework reads `sharedEvents` from the request exactly 4× per processRequest —
shared events are a first-class input of the eval dispatch path, not debug metadata.
lldb live-instance proof (same wrapper, both API families): `results/lldb_shared_events.txt`
— `eventPort` 12339 observed identically through `MTLSharedEventHandle` and
`IOSurfaceSharedEvent` (lines 35/51); instance ivars `value=42 symbolIndex=7 eventType=1
agentMask=1 sharedEvent=<IOSurfaceSharedEvent: 0x75c9018420>` with raw layout at
+8/16/24/32/40 (+16=42, +40=0x75c9018420=wrapper pointer) matching
`results/class_dump.txt` encodings.

## Caveats (why "(a) with caveats", not a bare "(a)")

1. **Path A consumption crash.** Attaching a populated `_ANESharedEvents` to a
   `_ANERequest` on the in-memory-MIL path crashes
   `-[ANEProgramForEvaluation processRequest:...block_invoke +1524]` (fault addr 0x10) —
   independently reproduced here (`results/pathb.txt` era runs; stack in docs/TRACE.md),
   matching libane's documented behavior. Signals exist and are cross-wired, but the
   current firmware/driver only honours them via the Path-B `intermediateBufferHandle`
   flow.
2. **Path B end-to-end blocked by toolchain here.** Client compile of every available
   model source failed (`results/pathb.txt`: `ANECCompile ... InvalidNetworkSourceFileName`;
   MIL dir → `Cannot load model.espresso.net`). coremltools 9 in the bench venv lacks
   `MLModel.compile`; no `coremlcompiler` (CLT-only install, no full Xcode). So the
   latency table carries `PATHB_ONLY` in the event column rather than measured numbers.
3. **Internal semantics partially inferred.** The per-eval `sharedEvents` reads are now
   traced (E7), but `symbolIndex`/`agentMask` roles and the firmware wait-loop remain
   inferred from encodings + crash/trace record; no disassembly-level proof on this box
   (SIP blocks aned attach; see FAILURES.md F2).

## Reference measurements
Baseline CPU-completion latency table (5 batch sizes, same machine):
`results/latency.md`. Laya-apple issue #45's 8.48ms cited only as upstream reference,
not measured here.

## Update 2026-10-07 (Phase 2 — `docs/P2-LANE-A.md`)

Follow-up runs on the same machine revise one caveat and confirm the verdict:

1. **Caveat 2 was the wrong wall.** The blocker was not "no Xcode toolchain":
   `+[MLModel compileModelAtURL:error:]` compiles locally CLT-only in <1 s
   (`results/p2_compile_at_url.txt`), and current bundles — old or freshly compiled —
   contain **no `model.espresso.net` at all** (`results/p2_bundle_diff.txt`). The legacy
   `_ANEClient compileModel:`/`loadModel:` door rejects every 27-era bundle at
   `_ANEEspressoIRTranslator` for exactly that file
   (`results/p2_espresso_net_wall.txt`). The live producer is `ANECompilerService.xpc`
   (MIL→`model.hwx`→aned, observed via root `fs_usage`).
2. **The verdict's primitive is production plumbing.** dtrace census on the public
   E5 path: `newSharedEventWithMachPort:` ×131, `enableLowLatencyWaitSharedEvent` ×37,
   `disableIOFencing` ×131 per steady-state predict window
   (`results/p2_census_e5_selectors.txt`) — the shipping stack gates engine work on
   the same mach-port shared-event counter measured here at ~62 µs crossing.
3. **First measured routing instance.** Over a 600-predict E5 loop `enginemon` shows
   GPU Energy 2.35 J, **ANE 0.0 mW / 0 handlers / 0 B DCS** despite compiled ANE
   material (`results/p2_enginemon_gpu.txt`) — the router sent a model with ANE
   eligibility to GPU. Lens-validated 2026-10-08: ANE-exclusive `SOC-NI9 ANEXL U`
   / `SOC-NI8 ANE UP` (validated 0→14.7k/13.8k on known-ANE work, EXP-027 AN-POS)
   read 0 in this window ⇒ true negative, not instrument blindness. E2E event timing now waits on driving the `ANECompilerService`
   / E5 producer path, not on the espresso door (lane A2b, `docs/P2-LANE-A.md` §7).
4. **kANEF keys confirmed present in-process**, both targets
   `kANEFDisableIOFencesUseSharedEventsKey`, `kANEFEnableFWToFWSignal`, plus block
   encoding `v24@?0@"IOSurfaceSharedEvent"8Q16` (`results/p2_kanef_strings.txt`);
   behavior probes deferred to a loaded-program slice.

Caveat 1 (Path A consumption crash) unchanged; Path-B E2E `event_extra_ms` still
GAP, now GAP-declared against the producer path rather than the toolchain.
