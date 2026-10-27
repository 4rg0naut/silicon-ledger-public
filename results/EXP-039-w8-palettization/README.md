# EXP-039 — w8 palettization A/B on M5 Max: the 4.8x is an M4 number, not a law

## Question
EXP-005 step 5 (Mac mini M4, h16g): the w8-palettized + fp16-compute Granite-Embedding-97M build
ran **4.8x slower** than fp16 on the ANE (19.48 vs 4.05 ms warm). That number circulated as if it
were a property of palettization. Was it re-measured on M5 Max (different compiler generation,
h17c)? This closes that cell.

## Method
`ports/export_granite_w8_fp16.py` (the EXP-005 script, restored from git history where P3 moved it
from bench/ to ports/; two portability patches: toolchain path globbed, ARCH resolved from
hw.model — Mac17 -> h17g). Rebuilt the identical artifact class on the Studio: zoo
`KMeansPalettizerConfig.presets.w8()`, 48 linears, seed 0, fp16 load, S=128. Ran both bundles
through `tools/granite-runner` (`--compute neuralEngine`, 10 warm discarded by protocol, n=110,
dump-latencies JSON) **in one window, consecutively** — matched A/B; raw:
raw/lat-fp16-20261026T233525Z.json, raw/lat-w8-20261026T233525Z.json.
Window: LOADED (oMLX up, loadavg ~2.7; QUIET-KEY in capture header). Both arms share the window,
so the RATIO is the claimable number; absolute ms are stamped-loaded.

## Results (M5 Max, h17c, macOS 27.0.1/26A434)
| arm | warm p50 | p95 | min | load | size | min cosine | max err |
|---|---|---|---|---|---|---|---|
| fp16 s128 | **12.17 ms** | 15.98 | 9.63 | 202 ms | 195 MB | 0.999957561 | 1.46e-03 |
| w8 + fp16 s128 | **19.11 ms** | 24.18 | 15.15 | 1663 ms | **167 MB** | 0.999383390 | 6.09e-03 |

**Palettization is still a loss on this graph on M5 Max — but the penalty is 1.57x, not 4.8x.**
The M4 cell (4.8x) does not carry. Load time penalty also shrinks (8.2x here vs 39x on the M4
capture). Numerics match EXP-005's character (same gate PASS, same error magnitude) — this is the
same artifact class, not a regression.

Structural detail visible only on h17c: the compiler emits per-op warnings on the embedding-table
I/O cast (`ANE I/O op can only do F16 MemRef <-> F32 Tensor cast`, element type list
fp16/f8E4M3/si8/ui8/si16/ui16) and delegates those to MPSGraph — the h17c pipeline splits the
w8 graph differently than h16g did (14 ANE regions recorded vs EXP-005's corrected 13 for h16g;
fp16 v3 was 1). Direction of the shrink is consistent with "more of the graph absorbed per
region, fewer LUT-reconstruction churn points", but with the ANE-interrupt counters unprivileged
on this host we stop at the timing statement.

## Claim we can now make (and put in sidekick #104 / hollance draft)
1. W8A16 weight-only palettization is a **storage lever, not a compute lever** on this graph on
   BOTH h16g and h17c — negative result replicates.
2. The magnitude is machine-pinned: 4.8x on M4 mini vs 1.57x on M5 Max under matched same-window
   A/B. Any universal "int8 makes ANE N times slower" claim inherits our mistake of quoting one
   box.
3. The double-int8 compute-rate question (W8A8) remains open and unchanged: activation
   compression is a different, riskier change (EXP-005 step 5 rationale stands).

## Follow-ups
- energy cell: **DECLINED-window (protocol)** — quiet_probe stamps "measurement host is LOADED;
  energy arms invalid" and it was: ambient GPU load ~29 W (oMLX) dwarfs the runner's few-watt
  delta; the matched interleaved A/B (raw/em-ab2.json, markers raw/em-ab2-marks.log, summary
  raw/energy-ab-summary.json) yields an ambient-subtracted ratio of 0.79x with per-phase scatter
  larger than the signal — reported as inconclusive, NOT as "w8 cheaper". Re-run needs a
  certified-quiet window (same gate as EXP-038; the armed watcher covers EXP-037 cells only —
  extend when triggered). First (unadjusted) attempt raw/em-ab.json discarded for burst-boundary
  ambiguity; the wrapped re-run fixed boundaries via idle-gap markers.
- what the loaded window DOES prove: lane placement per phase from the ANE lens —
  ANE-LNK0/1 events 142–267 M in every phase of both arms (raw/energy-ab-summary.json): both the
  fp16 and the w8 build run on the ANE on h17c, w8 moving ~4% less warm link traffic than warm
  fp16 despite 1.57x the time (direction consistent with the halved weight stream; count-per-second
  is where the churn lives, matching EXP-005's interrupt-count finding).
- re-run both arms in a certified-quiet window when the operator cuts oMLX (removes the loaded
  window caveat on absolute ms + unblocks the energy cell).
- enginemon ANEXL U lens is validated on the Studio (EXP-037) — an ANE-attention-count run
  between regions would test the "less churn" hypothesis cheaply.
