# ANE eval latency — baseline (GPU||ANE CPU-completion), 5 batch sizes

**Machine:** Mac17,14 (M5 Max) · **OS:** macOS 27.0.1 (26A434) · **Date:** 2026-10-07
Raw: `results/latency.txt`. Harness: `harness/ane_sync_harness.m latency` (reuses
`harness/ane_bridge_mrr.m`, a retain-fixed copy of silicon-ledger-bench `ane_bridge.m`;
submodule left clean).

Workload per sample: Metal spin kernel (fixed ~duration matmul-shaped write loop) runs
concurrently with a pre-dispatched ANE eval of an fp32 conv-chain (ch=64, depth=8) in a
shared MIL program; 30 iterations, median reported.

```
sp      gpu_elems  eval_ms  baseline_total_ms  baseline_extra_ms  event_total_ms
128     65536      0.109    0.283              0.037              PATHB_ONLY
512     131072     0.095    0.342              0.020              PATHB_ONLY
2048    262144     0.119    0.435              0.037              PATHB_ONLY
8192    524288     0.150    0.704              0.053              PATHB_ONLY
32768   1048576    0.621    1.092              0.029              PATHB_ONLY
```

Definitions:
- `eval_ms` — standalone `evaluateWithQoS:` wall time, main thread.
- `baseline_total_ms` — GPU-submit → ANE-completion-block, CPU mach-port completion path
  (`ANERequestReceiver::FrameDone`, see docs/TRACE.md).
- `baseline_extra_ms` = `(eval_done − gpu_done) − eval_ms`, i.e. the CPU completion
  round-trip overhead the event path would need to beat. Measured floor: **0.02–0.05 ms**.
- `event_total_ms` — requires Path B (`intermediateBufferHandle`) dispatch to consume
  `_ANESharedEvents`; Path A consumption crashes (VERDICT.md caveat 1), so the column is
  blocked here (results/pathb.txt), not zero.

## Interpretation limits
- Reproduction: `ANE_STOP2=1 ./harness/ane_sync_harness latency` (events phase skipped;
  F11/F14). Re-verified 2026-10-07 19:52 after the F14 retain fix: numbers reproduce
  (eval_ms 0.10–0.63, extra 0.005–0.053ms).
- Laya-apple #45's 8.48ms figure is an upstream sleep/wake cost (mach-port message
  delivery after idle), NOT comparable to these spin-mediated numbers; cited as
  reference only, per task instruction.
- The event-path counter-crossing latency that *was* measured directly is porttest T2:
  GPU commit → wrapper-visible ≈ **62µs** (single sample, `results/porttest.txt`), i.e. the
  hardware hop itself costs well under the CPU round-trip floor — supportive of verdict
  (a), pending Path-B firmware consumption.
