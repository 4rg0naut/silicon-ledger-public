# #8 stage 3 findings — Metal counter surface on M5 Max vs M4 (unprivileged)

Probe: `silicon-ledger/bench/metal_counters.m` (build header has the command). Raw: `counters-m5.json`
(M5 Max, macOS 27.0.1 / 26A434); M4 mini output reproduced below (ran same source over ssh).

## What the Metal layer exposes

| | Apple M5 Max (this Studio) | Apple M4 (mini) |
|---|---|---|
| counterSets visible to user agent | `timestamp` only | `timestamp` only |
| counters | `GPUTimestamp` (1) | `GPUTimestamp` (1) |
| AtStageBoundary | True | True |
| AtDrawBoundary / AtDispatchBoundary / AtTileDispatchBoundary / AtBlitBoundary | False | False |

- `newCounterSampleBuffer` on the timestamp set succeeds unprivileged on both machines.
- Encoder compute sampling (`sampleCountersInBuffer`) is not permitted (AtDispatchBoundary False);
  calling it anyway aborts inside `AGXG17XFamilyComputeContext` with an assertion — expected API
  misuse, recorded for completeness.

## Verdict for the ladder

**Stage 3 is a dead end for GPU-NA attribution, identical on both machines.** There is no
tensor/NA pipe counter in the unprivileged Metal surface — no StageUtilization, no Statistic set,
no vendor sets at all beyond timestamp. The richer catalog most likely sits behind the same
entitlement wall as the gated IOReport channels (cf. mactop PR #75 note on entitled samplers).

Remaining ladder rung that can still yield a calibrated GPU-NA positive signal: **stage 4**,
privileged `powermetrics gpu_power + performance_counters` — folded into the EXP-022/#1 sudo
session (`results/EXP-024-engine-attribution/raw/sudo/sudo_capture.sh`; capture scratch:
`/Volumes/data/OpenFox/dev_m5max_re/exp024-raw/sudo/`). Stages 1/2/5 already executed (results in
`knowledge/ane/10-m5-attribution-signals.md`: UT histogram = trick; PerformanceStatistics has no
tensor/NA keys; PMP0/AGX group probing produced the ANE-side floors).

## Addendum (2026-10-06, plumbing smoke with rebuilt enginemon)

The Energy Model `GPU Energy` channel is readable UNPRIVILEGED on macOS 27: idle 259 mW,
~11.5 W during tensorops+oMLX activity (`--json sum.energy_mw`). `CPU Energy`, `GPU0`, `ANE0`
still read 0.0 — the earlier "rails gated" finding stands for THOSE, but gross GPU watts do
not need the sudo window after all. The quiet capture stays (powermetrics remains the primary,
process-attributed source), but the LADDER M5 GPU-rail row now has a second, unprivileged
source that can be re-taken any time.

## Side finding (bigger than this probe)

While preflighting the sudo capture, granite-runner on the rebake-p3 `h17g` bundle threw
`incompatibleCompiledAssetArchitecture(device: "h17c", asset: ["h17g"])`: **the M5 Max CoreAI
delegate identifies as `h17c`**. This explains the EXP-023 AOT `error 0` (see that record's
correction) and changes what architecture flag M5 AOT builds must use. `h15g` (M4-era default in
`sudo_capture.sh`) was wrong for this machine; script now passes the unspecialized `.aimodel`,
which loads and passes the numeric gate on cpuOnly (4.3 ms) and neuralEngine (10.1 ms) lanes.
