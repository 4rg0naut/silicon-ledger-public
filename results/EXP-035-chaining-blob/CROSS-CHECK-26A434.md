# EXP-035 cross-check — 26A434 selector census (2026-10-23, C8-C4)

Source: `ncm-run/bare/dev/c8_ane_c3probe.m` run on the M5 Max studio
(fingerprint `bda452aabd60bf26`), macOS 26A434. Full JSON:
`ncm-run/bare/results/2026-10-23T23-27-05Z-bda452aabd60bf26.json` (AI_dev repo).

## Chaining surface (our raw-IOKit sel-2 ground, ane-infer now MIT)

- `+[_ANEIOSurfaceOutputSets objectWithstatsSurRef:outputBuffer:]` — PRESENT
  (the ane-infer chaining-factory fix; `outputSetsWithBuffers:` alone was the
  crash path they patched). Instance init `-initWithstatsSurRef:outputBuffer:`
  and getter `-statsSurRef` also present.
- `+[_ANEChainingRequest chainingRequestWithInputs:outputSets:lbInputSymbolId:lbOutputSymbolId:procedureIndex:signalEvents:transactionHandle:fwEnqueueDelay:memoryPoolId:]` — PRESENT.
- `-[_ANEClient prepareChainingWithModel:options:chainingReq:qos:error:]` +
  daemon `withReply:` twin + `_ANEErrors programChainingPrepareErrorForMethod:` — PRESENT.
- `initOutputSetWithProcedureIndex:setIndex:signalValue:signalNotRequired:isOpenLoop:` (`_ANEOutputSetEnqueue`) — PRESENT.

Conclusion: everything ane-infer's framework-level chaining fix needs exists
on 26A434; our raw-IOKit `ANEProgramChainingPrepareArgs` (sel 2) remains the
same kernel entry the client `-prepareChainingWithModel:` wraps. Consistent,
no contradiction with EXP-035.

## Mutable weights (claimed macOS-27 API)

- `-[_ANEClient mapMutableWeightsForModel:andProcedure:mappedWeightsBuffer:size:error:]`
  (+ sync/unmap, `_ANEVirtualClient` XPC twins, direct
  `mapMutableWeightsBufferDirectForProcedure:bufferID:buffer:size:error:` on
  `_ANEProgramForEvaluation`) — PRESENT on 26A434 (not 27-only).
- BUT: for an in-memory-compiled program the procedure carries
  `mutableWeightsBufferID=0 size=0`; daemon map returns NO with nil error;
  `procedureInfoForProcedureIndex:0` returns an empty dict.
- Request `weightsBuffer:` IOSurface slot: accepted by eval, output unchanged
  when mutated → program does not consume it (constant-folded weights).
- Verdict: weight swap on 26A434 in-memory path = recompile via descriptor
  (measured <300 ms compile+load+eval, C8-T0), not mutable-map. Driver-side
  provisioning (or a program built with an external-weight MIL symbol) is the
  missing piece; revisit with ANECompilerService options if we ever need
  in-place swap.
