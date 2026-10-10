# macmon × enginemon cross-validation — session3 window (r3 matrix), 2026-10-05

Criterion #4 record. `macmon 0.8.2` (brew, JSON stream, `macmon_session3.jsonl`, 722
samples @1 Hz, `timestamp` epoch-ISO) run alongside the r3 calibration arms
(`r3_*.jsonl`, windows recovered from stream durations + file mtimes, UTC aligned).

## Agreement (independent instruments, same rails)

| arm | window | macmon gpu_power mean | enginemon GPU Energy (final Δ ÷ window) |
| --- | --- | ---: | ---: |
| idle | 30.4 s | 40.36 W | 40.62 W |
| cpu | 18.2 s | 36.07 W | 35.93 W |
| tensorops | 13.0 s | 45.63 W | 45.32 W |
| msl | 90.4 s | 66.93 W | 66.91 W |
| mps | 18.6 s | 61.15 W | 60.43 W |
| ane | 8.6 s | 37.84 W | 37.69 W |
| coreai | 2.9 s | 35.23 W | 37.48 W |

Every arm agrees within ~1–6% (shortest windows worst, as expected from macmon's own
batch cadence). The GPU rail is trustworthy at user level from two independent stacks.
Absolute floors are contaminated-by-design (oMLX resident GPU work): idle ≈ 40 W.

## Corroborations

- macmon reported `ane_power = 0.0` in **722/722** samples and `cpu_power = 0.0` in
  722/722 across arms that verifiably moved the ANE (our PMP0 floor-bin duty 82.9%) and
  heavy CPU (cpu arm). This independently confirms the macOS 27 **gating** of the Energy
  Model ANE/CPU rails at user level — macmon hits the identical wall (its code is the
  same IOReport API, unprivileged). Not an enginemon artifact.
- macmon `gpu_active_ratio` saturates ≈100% on every GPU arm including idle — the same
  "busy baseline by construction" state our UT-engagement numbers carry; on this machine
  active-% is only usable against its own in-session baseline.

## Disagreement found (and fixed) — FINDING, EXP-004 lesson

- First cross-check pass appeared to show enginemon idle at ~1.1 MW: the **v2.0 JSON
  stream emitted since-start CUMULATIVE totals in the per-interval `d`/`s.r` fields**
  while the facet schema documented them as per-interval deltas. macmon's per-sample
  values are per-interval, so the instruments disagreed by design, not by measurement.
  Caught only because two instruments existed — the exact reason criterion #4 exists.
- Fixed in **enginemon v2.1** (per-interval `d`/`s.r` via reported-baseline subtraction);
  schema `x_stream_record … properties.ch.items.properties.d` now carries the version
  note so r2/r3-era captures (cumulative) parse correctly. v2.0 `sum.energy_mw` was
  always correct (computed from window totals) — prefer it for historical files.
- Consequence checked: the calibration conclusions in `FINDINGS` / enginemon README use
  final-total ÷ window and per-window duty — unaffected by the stream bug.

## Divergences still open

- macmon exposes `ram_power`/`sys_power` live while enginemon does not subscribe DRAM
  rails (Energy Model `DRAM0` is gated at user level anyway — mactop fb2caf8 uses SMC
  `PZD1` instead). Candidate enginemon v2.2 addition: SMC PZD1 for DRAM context.
- macmon `cpu_usage_pct`/per-core ratios (user-visible via task/thread APIs) fill the
  CPU-activity slot while the CPU energy rail is gated — matches the criterion-#3 signal
  design (CPU = thread CPU-time + CPU Energy when entitled).
