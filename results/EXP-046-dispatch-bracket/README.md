# EXP-046 — dispatch-to-present bracket, per machine

Question: where does wall time actually go between `commit` and something hitting the display?
Closes the P2 gap-flag (spine API-172 pinned GPU-submit floors with no bracket); hardware-floor
bounds only — no runtime involved, no frame ever vouched.

Instrument: `retro_probe p` (EXP-045 harness, INSTR-206) — empty tiny kernel,
CADisplayLink-free bracket: host `commit→waitUntilCompleted` percentiles + GPU `start/end`
timestamp span, load=0 (idle) and load=1 (n-1 default-class loaders) passes.

## Rows (per-machine protocol — never cross-paired)

| machine | window | commit→complete p50/p99 µs | GPU-exec span p50/p99 µs |
|---|---|---|---|
| M5 Max Studio | 2026-10-27T13:24Z, **loaded** (loadavg 3.3, upper-bound), WindowServer present (pid 498) | 113 / 215 (idle pass) · 121 / 215 (loaded pass) | 2.00 / 17.50 · 7.25 / 59.75 |
| M4 mini | 2026-10-27T13:38Z, uptime-gated loadavg 1.2 (not quiet-probe-certified) | 185 / 720 (idle pass) · 239 / 769 (loaded pass) | 3.46 / 221 · 3.08 / 131 |

[studio raw](../EXP-045-closed-claims/raw/studio-ABp-eb-20261027T132418Z.txt) ·
[mini raw](../EXP-045-closed-claims/raw/mini-quiet-P46-20261027T133843Z.txt) ·
ledger row [MEASURE-170](../../knowledge/ane/06-measurement.md)

## Reading

- GPU-exec floor on an empty submit is **2–3.5 µs p50** on both chips — the number to attack any
  "dispatch overhead" story with: M1-era claims of 33–50 ms *frame* costs cannot be GPU submit
  floor; they live in host/compile/present layers.
- The bracket itself is **host-dominated**: commit→complete is 30–60× the GPU span; loaded windows
  move GPU p99 far more than idle p50 (contention tail, not floor).
- **Present half (vsync): partial.** Studio bracket ran in a GUI session (WindowServer present) —
  present-stage cost is bounded above by host round-trip; a display-attached CADisplayLink
  instrument has not been run (deferred, decider: owner with a monitor-attached window).
- mini p99 tails (720–769 µs) on ~1.2 load: 16 GB box background churn, not submit physics.

## Reproduce

```sh
cd results/EXP-045-closed-claims/harness
./retro_probe p                       # Studio bracket
scp retro_probe mini:/tmp/ && ssh mini '/tmp/retro_probe p'   # mini bracket
```
