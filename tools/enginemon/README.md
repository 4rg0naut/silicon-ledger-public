# enginemon — which engine actually ran your work (CPU / GPU / ANE), no root

A single-file C tool that reads Apple's **IOReport** counters directly and reports
per-engine activity: CPU/GPU power, and **ANE memory traffic + interrupt counts**.

```bash
clang -O2 -o enginemon enginemon.c -framework CoreFoundation

./enginemon --list                      # every engine channel it can see
./enginemon --interval 500 --duration 5 # sample for 5 s
./enginemon --interval 500 --duration 25 -- <command> [args...]   # sample while a workload runs
```

## Why this exists

`powermetrics` needs **sudo**. `xctrace`'s `ane-hw-intervals` is **blind to Core AI graphs**
(measured: 0 intervals, while a Core ML control in the same session logged 1310). And
`preferredComputeUnitKind: .neuralEngine` turned out to run on the **GPU** anyway. Placement
needs an instrument that is unprivileged, trustworthy, and not tied to one runtime.

IOReport is private but stable, and **an unprivileged process can list, subscribe to and
sample it** (verified: euid 501, macOS 27.0, M4). No helper, no entitlement.

## The two traps it is built to avoid

Both were hit while developing it, and both would have produced a *confident wrong answer*:

1. **`Energy Model → ANE` is frozen.** It reads a constant (10945781) and never changes — not
   under idle, not under a Core ML workload that provably uses the ANE. Reporting its zero as
   "the ANE was not used" is a **fabricated negative**. The tool labels it as frozen and tells
   you to use other channels.
2. **`SoC Stats → ANE_*_TRIG` is a free-running 24 MHz clock.** It advances by exactly
   `elapsed × 24e6` (5.46 s → 131110395 ticks) *regardless of load*. It looks like activity and
   means nothing. The tool excludes these channels.

## What actually works (validated)

Controls run back to back, same machine, same session:

| channel | idle | Core ML `compute_units=ALL` (known ANE) |
| --- | ---: | ---: |
| `AMC Stats → ANE DCS RD` | 0 B | **128–171 GB** |
| `AMC Stats → ANE NRT AF RD` | 0 B | **184 GB** |
| `Interrupt Statistics`, subgroup `ane 0`, 2nd-level count | 0 | **24,538 – 37,368** |
| `PMP → ANE0 RD` | 0 events | 29,252 |
| `Energy Model → GPU Energy` | ~15 mW | ~14 mW (GPU idle — the ANE did the work) |
| `Energy Model → ANE` | 0 | **0** ← dead channel |

**Read `AMC Stats` (bytes moved) and the `ane 0` interrupt counts.** Those are the signals
that separate "the ANE worked" from "the ANE was idle".

## Reading the output

```
SUMMARY (over 9.11s)
  CPU Energy            0.0 mW
  ANE                   0.0 mW   (this channel is frozen on M4 -- use AMC/interrupt counters, not this)
  GPU Energy           14.0 mW
  ANE activity   128235228928 B moved, 37368 interrupts
```

- **`ANE activity` > 0** → the ANE moved that much memory and took that many interrupts.
- **`ANE activity` = 0** with high `GPU Energy` → the GPU did the work.

## Caveats

- The ANE interrupt rows belong to **subgroup `ane 0`**. The `dart-ane 0` rows stay at 0 for
  ANE compute; the tool tracks both, so read the subgroup column.
- Energy channels are cumulative; deltas come from `IOReportCreateSamplesDelta`, not from
  hand-differencing samples.
- Private API: symbols are resolved with `dlsym` at runtime, so the tool fails softly
  (`IOReport symbols missing`) rather than breaking at link time if Apple moves things.
- Channel availability is SoC/OS specific. Run `--list` first on a new machine; a channel that
  does not exist here may exist there, and vice versa.
