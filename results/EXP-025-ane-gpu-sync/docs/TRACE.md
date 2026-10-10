# Dynamic trace of the ANE completion path — macOS 27.0.1 (26A434), Mac17,14

## Channels available under SIP (and what was blocked)

| channel | status | evidence |
|---|---|---|
| `dtrace -p` pid-provider on **own harness** (PRIMARY (a)) | **WORKS** | `results/dtrace_ane_methods.txt.gz` (151 ANE method entries), `results/dtrace_primary.txt.gz`; scripts `harness/trace_ane_attach.sh`, `harness/trace_primary.sh` |
| lldb inspect of own-harness `_ANEShared*` instances (PRIMARY (a)) | **WORKS** | `results/lldb_shared_events.txt`; script `harness/inspect.sh` |
| `dtrace -p $(pgrep aned)` pid-provider | **BLOCKED** — "failed to grab pid 998" | paste 2026-10-07 (chat log) |
| `lldb -p $(pgrep aned)` | **BLOCKED** — "Not allowed to attach to process" | paste 2026-10-07 |
| kernel providers (syscall/fbt/io/proc/sched/lockstat/csm) | **ABSENT** | full `sudo dtrace -l` dump, 11,153 probes, `results/dtrace_probes.txt.gz`; only `profile` (13) + userspace statics survive |
| `log show -p aned` (unprivileged, after `log config --mode level:debug,persist:debug --process aned`) | **WORKS** | `results/aned_logshow_eval.log.gz` (2,766 lines covering eval windows) |
| `sudo dtrace profile-NNNN sampling of aned` | available (not required; port-test evidence sufficient) | probe dump lines 31–41 |

## What aned logs during eval (the completion vocabulary)

`results/aned_logshow_eval.log.gz` (process scope DEBUG, unprivileged read):

```
ANEDriver Device Open succeeded with usage type: 2
Calling ANEDeviceOpen( deviceUsageType=2 : programHandle=0 )
ANEDeviceClose() self.usecount=0 : self.device=0x0
ANEServicesDevice::ANE_ProgramCreate, input buffer count: 1, output buffer count: 1
```

(counts in this capture: 50 "Device Open succeeded", 18 "Calling ANEDeviceOpen",
19 "ANEDeviceClose", one `ANE_ProgramCreate` line per eval session.)

Negative finding: across 2,766 lines there is **no log line containing
signal/wait/event/fence/FrameDone/complete** — completion is not logged by name in the
armed debug scope. The observable lifecycle is device open/close per eval session
(8s idle-close cadence).

## Client-side completion path (from own-process crash forensics)

Crash reports (harness = non-Apple binary, fully inspectable) expose the in-process
completion machinery that the daemon-side trace cannot:

```
_-[_ANEProgramForEvaluation processRequest:model:qos:qIndex:modelStringID:options:returnValue:error:]_block_invoke +1524
ANEServicesFrameProcDirect(void*, ANE::ANERequestReceiverRequest*) +2612
ANE::ANERequestReceiver::FrameDone(void*, int, unsigned long long*, int) +1044
IODispatchCalloutFromCFMessage +280
__CFMachPortPerform → CFRunLoop
```

(`~/Library/Logs/DiagnosticReports/ane_sync_harness-2026-10-07-18*.ips`)

Findings:
1. ANE frame completion is an **IOKit mach-port message into the submitting process's run
   loop** — `ANERequestReceiver::FrameDone`. Not a Metal callback, no GPU-family code in
   the chain (no MetalOS/GPUFamily frame anywhere in any crash or trace).
2. Completion-block stack slots (the `error:` out-var) must outlive `evaluateWithQoS:` or
   the delayed run-loop delivery dereferences dead stack → SIGSEGV 0x10 (fixed by
   heap/static slot: `harness/ane_bridge_mrr.m` `ane_bridge_eval`).
3. `evaluateWithQoS:` must be called on a thread whose run loop services the mach port —
   calling it from a Metal completedHandler thread crashed (`processRequest ... _block_invoke`,
   IODispatchCallout frame) while main-thread eval is clean (`results/latency.txt`).
4. Attaching `_ANESharedEvents` to a request on the in-memory-MIL path (Path A)
   reproduces libane's documented unconditional crash exactly
   (`processRequest:_block_invoke +1524`, address 0x10) — independent re-verification
   on macOS 27.0.1 / M5 Max that shared-events are firmware-gated to the Path-B
   `intermediateBufferHandle` (KB claim: `/Volumes/data/OpenFox/dev_m5max_re/silicon-ledger-public-staging/knowledge/ane/02-private-api.md` §5).

## PRIMARY channel results (a) — own-process dtrace + lldb (completed 26-10-07 19:5x)

### dtrace pid-provider on our own harness (user-built → attach allowed)
`harness/trace_ane_attach.sh` (sudo) spawns the harness (`ANE_STOP2=1 ANE_REPS=40 latency`)
and attaches `dtrace -p PID -s harness/ane_ane_methods.d`. Result:
`results/dtrace_ane_methods.txt.gz` — **151 distinct ObjC method entries on the
AppleNeuralEngine module**, dispatch vocabulary quoted:

```
+[_ANEClient sharedConnection]                                        1
+[_ANEInMemoryModel inMemoryModelWithDescriptor:]                     1
+[_ANERequest requestWithInputs:inputIndices:outputs:outputIndices:weightsBuffer:perfStats:procedureIndex:]                1
-[_ANEInMemoryModel compileWithQoS:options:error:]                    1
-[_ANEInMemoryModel loadWithQoS:options:error:]                       1
-[_ANEInMemoryModel setIntermediateBufferHandle:]                     1
-[_ANEProgramForEvaluation programWithController:intermediateBufferHandle:queueDepth:] 1
-[_ANERequest initWithInputs:...:procedureIndex:sharedEvents:transaction  1
                                 (line truncated at dtrace's 96-char key limit; full
                                  selector per results/class_dump.txt)
-[_ANEInMemoryModel evaluateWithQoS:options:request:error:]        1686
-[_ANEProgramForEvaluation processRequest:model:qos:qIndex:modelStringID:options:returnValue:error:] 1686
-[_ANERequest sharedEvents]                                        6744
```

Findings: (i) the full MIL→compile→load→eval dispatch chain is visible in-process;
(ii) **every eval reads `sharedEvents` exactly 4× from the request inside the dispatch
path** — the framework consults shared events unconditionally per processRequest,
independent of whether events are attached; (iii) `IOSurfaceGetID`/`IOSurfaceClientGetID`
×3372 (2 per eval, input+output surface resolution). The `objc$target` provider itself
is SIP-denied ("probe description objc47593:_ANE*::entry does not match any probes.
System Integrity Protection is on" — results/dtrace_primary.txt.gz tail), hence the
pid-provider symbol-pattern approach.

Two enabling discoveries: `dtrace -c` fails for this module
("pid$target:AppleNeuralEngine::entry does not match any probes") because probes are
enabled pre-`main`, before the harness dlopens AppleNeuralEngine — attach-after-spawn
fixes it; and full latency mode dies in the PathA event phase in ~100ms (F11), so the
inferior is kept live with `ANE_STOP2=1 ANE_REPS=40`.

Earlier `dtrace -c` runs (`results/dtrace_primary.txt.gz`, latency+porttest windows) had
already captured the bridge side live: `-[IOSurfaceSharedEvent initWithMachPort:]` ×2,
`-[IOSurfaceSharedEvent eventPort]` ×3 (latency run), and in porttest run
`-[IOSurfaceSharedEvent setSignaledValue:]` ×2,
`-[IOSurfaceSharedEvent waitUntilSignaledValue:timeoutMS:]` ×2,
`-[IOSurfaceSharedEvent signaledValue]` ×4, plus IOConnectCallMethod selector counts
(0,2,5,6,7,9×27,13,14,16,28,32,36,38,44,256,258,261) — selector 9 ×27 = the per-eval
IOKit round-trip in the eval loop.

### lldb live-instance inspection (no sudo; own binary)
`harness/inspect.sh` → `results/lldb_shared_events.txt`. Live `_ANESharedSignalEvent` /
`_ANESharedWaitEvent` instances constructed in-process around a real
`IOSurfaceSharedEvent` built from an `MTLSharedEventHandle.eventPort`:

```
_ANESharedSignalEvent: { value=42 : symbolIndex=7 : eventType=1 :
    sharedEvent=<IOSurfaceSharedEvent: 0x75c9018420> agentMask=1 }
_ANESharedWaitEvent: { value=43 : sharedEvent=<IOSurfaceSharedEvent: 0x75c9018420> }
(unsigned long long)[$sig value]                       = 42
(unsigned int)[$sig symbolIndex]                       = 7
(unsigned int)[$sw eventPort] / [(id)[$sig sharedEvent] eventPort] = 12339  (both wrappers)
raw +16 (_value)     = 42
raw +40 (_sharedEvent)= 505883493408 = 0x75c9018420    (matches wrapper pointer)
```

Ivar layout at offsets 8/16/24/32/40 confirmed against `results/class_dump.txt`
encodings (I/Q/Q/q/@). Secondary-wrapper `setSignaledValue:` raised an ObjC exception
in the inferior (recorded; cross-write direction proven by porttest T3 instead).

## Metal participation

Does `aned` touch Metal/GPU? **No.** aned links no Metal (otool), no Metal frames in any
trace, and the daemon-side API nouns are all `ANEServicesDevice::` / `ANEDriver`.
Metal's role is entirely client-side: the GPU writes the counter that the ANE-side
`IOSurfaceSharedEvent` wrapper reads (porttest T2 PASS), via the shared kernel port object.
