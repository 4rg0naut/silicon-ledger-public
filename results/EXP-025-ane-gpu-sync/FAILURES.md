# FAILURES LOG — ANE↔GPU sync primitive discovery
Machine: Mac17,14 (M5 Max) · macOS 27.0.1 (26A434) · dates 2026-10-07
Format: tried → broke → why. Everything below is from actual terminal output in this
session unless flagged as upstream (KB citation).

## F1. Task premise vs actual OS
- Tried: run the plan written for macOS 26.x M5 Max.
- Broke: box reports **macOS 27.0.1 (26A434)**, not 26.x.
- Why: assumption drift — the 27 SDK also dropped `IOSurfaceSharedEvent` header
  exposure (runtime class only), so no compile-time reference to the bridge type is
  possible; all bridge work had to go through `objc_getClass`/dlsym probes.

## F2. SIP-blocked dynamic tracing channels (criterion 3 findings)
- `sudo dtrace -p $(pgrep aned)` → **"failed to grab pid 998"**. SIP denies pid-provider
  attach to Apple-platform binaries even as root.
- `sudo lldb -p $(pgrep aned)` → **"Not allowed to attach to process"**. Same cause.
- Kernel providers: full `sudo dtrace -l` (11,153 probes, `results/dtrace_probes.txt.gz`)
  shows **no syscall/fbt/io/proc/sched/lockstat providers** on this config — only
  `profile-*` + userspace statics. Mach/io_connect call tracing for aned is impossible
  without disabling SIP.
- `log stream` launched from zsh produced 30-byte empty logs
  (`results/aned_stream.log`): **`log` is a zsh builtin** and shadowed
  `/usr/bin/log`. Also: `echo ====` aborts zsh (=expansion); `head -c -1` unsupported
  (BSD). Fixed by absolute path; switched to `log show` after the debug-config window.

## F3. Framework binary is a shared-cache stub
- Tried: `nm -gU AppleNeuralEngine.tbd`-style on-disk analysis of the framework.
- Broke: 0 exported symbols listed for class search.
- Why: on-disk Mach-O is a stub; real code lives in the dyld shared cache. Pivoted to
  in-process runtime enumeration (`harness/ane_class_dump.m`, 10,398 classes scanned,
  exactly 3 `_ANE*Shared*` matches → `results/class_dump.txt`).

## F4. ObjC runtime dump: wrong method polarity
- Tried: dumping `-initWithSharedEvent:` on `_ANESharedSignalEvent` class methods.
- Broke: "unrecognized selector" / method missing from listing.
- Why: initial dumper used the class object only; instance methods live on the class,
  class methods on the metaclass. Fixed polarity handling in `ane_class_dump.m`.

## F5. Metal shader compile errors
- `atomic_float` / bare `fabsf` rejected by MSL → fixed with
  `#include <metal_stdlib>` and explicit `device float*` types.

## F6. Foundation API misuse in harness
- `NSCalendar stringFromDate:` → unrecognized selector (that's DateFormatter in modern
  SDKs); replaced with `strftime`.

## F7. MIL `InvalidMILProgram` — pointer-width bug
- Tried: pass compiled MIL blob via `int len` upcall from Swift shim.
- Broke: framework read garbage length, program rejected.
- Why: FFI signature expected `size_t*`; `int` spilled the blob pointer on the stack.
  Fix: `size_t len`. (Blob itself was byte-identical to bench `MIL.swift` output —
  verified by diff against `/tmp/mil_expected.txt`.)

## F8. Eval SIGSEGV in `objc_retain` (+72 of evaluateWithQoS)
- Tried: reuse silicon-ledger-bench `ane_bridge.m` verbatim.
- Broke: crash in object retain during eval.
- Why: ObjC factory methods return autoreleased objects; the C bridge never retained
  model/tmpDir/IOSurface arrays, so they died before the eval phase. Fix:
  `harness/ane_bridge_mrr.m` adds explicit `CFRetain` (MRR = manual retain/release);
  original submodule file left untouched. Follow-on: `ane_bridge_free` hit SIGTRAP in
  `CF_IS_OBJC` on a dead NSString → free call dropped, tmpDir retained too.

## F9. Delayed completion block reads dead stack
- Tried: pass `&error` (stack slot) into the eval completion block.
- Broke: delayed mach-port delivery (`ANERequestReceiver::FrameDone`) wrote after the
  frame unwound → SIGSEGV. Fix: `static NSError *s_e` slot in `ane_bridge_eval`.

## F10. Eval from Metal completedHandler thread crashes
- Tried: dispatch ANE eval from the GPU completedHandler (the natural event wiring).
- Broke: `processRequest ... _block_invoke` crash — `evaluateWithQoS:` must run on a
  thread whose run loop services the ANE mach port. Fix: baseline loop spins
  (`usleep(50)`) until the handler stamps completion, then main thread calls eval.
  This is a *finding*: any event-driven design must marshal to a run-loop thread, or
  use Path B where the firmware consumes the event, not the client thread.

## F11. Path A shared-events consumption crash
- Tried: attach populated `_ANESharedEvents` (signal+wait wrappers) to `_ANERequest`
  on the in-memory-MIL path via `setSharedEvents:`.
- Broke: `-[ANEProgramForEvaluation processRequest:...block_invoke +1524]`,
  fault address 0x10 — deterministic.
- Why: matches libane's documented unconditional crash; shared-event fields are only
  honoured by the Path-B `intermediateBufferHandle` firmware flow (KB:
  `/Volumes/data/OpenFox/dev_m5max_re/silicon-ledger-public-staging/knowledge/ane/02-private-api.md` §5).
  Primitive itself is fine — porttest T2 proves the counter crossing independently.

## F12. Path B compile blockers (end-to-end event test not completed here)
- MIL directory to client compile → `Cannot load model.espresso.net`.
- System `mlmodelc` handed to `ANECCompile` → `InvalidNetworkSourceFileName`
  (stale Espresso IR expectation; `results/pathb.txt`).
- coremltools 9 (bench venv) exposes no `MLModel.compile`; `coremlcompiler` binary
  absent (Command Line Tools only, no full Xcode on this box).
- Net effect: latency table event columns are `PATHB_ONLY`, not measured.

## F13. sudo interactivity
- sudo commands require the user's password in this session; user chose to paste
  outputs manually (dtrace probe dump `results/dtrace_probes.txt.gz` is user-generated).
  `sudo log config --mode level:debug,persist:debug --process aned` needed this path.
  Later trace scripts (`trace_primary.sh`, `trace_ane_attach.sh`, `inspect.sh`) were
  designed for the user to run with sudo in their own terminal.

## F14. Latency-mode eval crash regression — delayed completion dereferenced freed options dict
- Tried: re-run `latency` mode after the session's tooling work (binary unchanged since the 19:03 good run).
- Broke: deterministic SIGSEGV 0x10 at `-[ANEProgramForEvaluation processRequest:...block_invoke +1524]` on the ANEServices run-loop thread; one-shot eval survived (process exits before delivery).
- Why: `@{}` options dict and (for later batches) the `_ANERequest` were autoreleased — under GPU load the completion block lands after the pool drains and memory is reused. The 19:03 pass was allocator luck. Fix in `ane_bridge_eval()` (harness/ane_bridge_mrr.m; mirrored in harness/ane_bridge_dbg.m): static CFRetained options dict + per-eval `CFRetain(k->request)`; verified with 3× ANE_STOP1 + 2× full 5-batch ANE_STOP2 runs clean, numbers reproduce the table (eval 0.10–0.63ms, extra 0.005–0.053ms).

## F15. `dtrace -c` cannot probe AppleNeuralEngine methods
- Tried: `sudo dtrace -c harness/ane_sync_harness -s harness/ane_primary.d` with `pid$target:AppleNeuralEngine::entry`.
- Broke: "does not match any probes" — with `-c` probes are enabled pre-`main`, before the harness dlopens the framework (IOSurface probes worked because it is link-time).
- Also: full latency inferior dies in the PathA event phase (F11) within ~100ms — attach window too short, first attach attempts hit "failed to grab pid".
- Fix: spawn-then-attach (`harness/trace_ane_attach.sh`) with the inferior kept alive via `ANE_STOP2=1 ANE_REPS=40` (reps loop added to latency mode); attach at +1s succeeds, END aggregations flush on target exit.

## F16. macOS D language lacks `strstr`
- Tried: predicate `strstr(probefunc, "-[")` in the .d script.
- Broke: "operator || requires operands of scalar type" (line 16) — built-in missing on macOS dtrace.
- Fix: function-name pattern matching in the probe description instead: `pid$target:AppleNeuralEngine:-*:entry` / `:+*:entry` (ObjC method impls are symbols prefixed `-[`/`+[`). Worked: 151 distinct methods captured.

## F17. msgSend selector census unreliable on macOS 27
- Tried: census of all `objc_msgSend` entries via `copyinstr(arg1)` with `-c`.
- Broke: thousands of "invalid address ... in action #2" errors — msgSend entries resolve to `libobjcMsgSend.dylib` fast-path variants where arg1 is not always the selector string; census came back partially empty.
- Why/fix: method-name evidence taken from the pid-provider module probes (F16 pattern) instead — authoritative `-[Class sel]` symbols; `results/dtrace_ane_methods.txt.gz` census kept as supplementary with this caveat.
