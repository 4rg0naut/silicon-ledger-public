# EXP-032 C-67 — per-eval counters: pulse map of the ANE doorbell

Captured 2026-10-23 (studio 11:34–11:39Z session + mini cross-check). Two machines,
three client paths, two program shapes, 18 enginemon captures. Raw streams in `raw/`,
joined table in `pulse_table.tsv`.

## Question

EXP-031 closed per-eval kANE counters as Apple-platform-entitled-only (CORE-009).
EXP-024 calibrated M5 whole-engine duty signals but never published a **per-eval**
rate. C-67 asks: on this box, can any unprivileged IOReport channel count
*evaluations*, and if not, what actually modulates the rate?

## Protocol

- Workloads: `ncm0 anectx --iters 20000` (S=32 parity kernel, 20,000 bridge-call
  evals), `ncm0 anectx --field` (S=160 unified kernel, exactly 100 evals, 8 fresh
  processes), `ncm0 anectx --iters 30000` under `enginemon --all`; CoreML control:
  `coreml_run minilm128.mlmodelc 40000` (computeUnits=cpuAndNeuralEngine, wall
  26.6–26.9 s/run × 3). Mini: identical `--iters 20000` build and enginemon binary
  rebuilt on-box.
- Sampler: `enginemon --interval 100 --json` (v2.1, this repo), one capture per run,
  plus idle bookends. enginemon exits with its child; windows in the table are
  measured sample sums, not nominal durations.
- Box-journal prereq: `ncm0 bench` sanity passed before timing windows (~3.5 s
  healthy). Eval counts are ledger-known: ncm0 auto-wrote stamped ledgers per run
  (studio `2026-10-23T11-34-52Z/11-34-56Z/11-35-00Z-bda452aabd60bf26` S=32,
  `11-35-02Z…11-35-16Z-bda452aabd60bf26` field ×8, `11-37-15Z` 30k — live in
  ncm-run workspace `ncm-run/bare/results/` at commit e7536a5, build release;
  mini `2026-10-23T11-39-23Z-057b28dd036ddbe8` on-box, stdout witness in
  `raw/mini_p32.work.log`).
- Provenance: workdir commit e7536a5 (ncm-run), build_config=release, corpus/seed
  fixed inside ledgers; enginemon from this repo `tools/enginemon/` (rebuilt
  `clang -O2 … -framework CoreFoundation` this session); machines: Mac17,14
  M5 Max 27.0.1/26A434 fingerprint bda452aabd60bf26, Mac16,10 M4 27.0.1/26A434
  fingerprint 057b28dd036ddbe8.

## Findings

### 1. Interrupts: M5 dead on BOTH paths; M4 alive on the direct path

`Interrupt Statistics (by index)` first/2nd-level handler counts, summed per capture:

| capture | channel | fires | per eval |
| --- | --- | ---: | ---: |
| M5 direct S=32 20k×3, 30k×1 | `dart-ane0 0` | **0** | 0.000 |
| M5 CoreML 40k×3 (26.9 s, ANE lanes confirm ANE busy) | `dart-ane0 0` | **0** | 0.000 |
| M4 direct S=32 20k (same binary+workload) | `ane 0` | **29,299** | **1.465** (peak 2,054/100 ms) |
| M4 idle 9.1 s | `ane 0` | 2 | — |

The M4 row validates the observer on the exact direct-API path that was silent on
M5 — the M5 zeros are **gated, not misread** (matches EXP-024 `dart-ane0 stay 0`
note and the M5 README caveat; now with dual-path controls and a same-workload
positive control). This extends MEASURE-012 (which was CoreML-on-M4 only):
M4 fires ~1.46 interrupts/eval through the direct `_ANEInMemory` path too.
Nothing modulates the M5 rate — on this OS/driver the interrupt lane is simply
closed to user observation for both client paths (kernel trace behind sudo/SIP;
Thread-1 territory, EXP-031 C-64 pack).

### 2. The per-eval counter that DOES work on M5: SOC-NI8/NI9 lanes

Per-interval deltas summed over each capture (columns `NI8_ANE_UP`/`NI9_ANEXL_U`):

| path/shape | NI9 ANEXL U /eval | spread ×N | NI8 ANE UP /eval | DCS BW ANE L0 RD+WR /eval |
| --- | ---: | ---: | ---: | ---: |
| direct S=32 (20k, n=3) | **0.488–0.503** | ±1.5% | 0.465–0.479 | 0.81–0.86 |
| direct S=32 30k `--all` | 0.480 | — | 0.465 | 0.66 |
| direct S=160 field (100 evals, n=8) | **1.00–1.06** | ±3% | 0.92–1.04 | 68.9–85.7 |
| CoreML minilm128 (40k, n=3) | **2.889–2.915** | ±0.5% | 2.889–2.915 | 2.94 |

The rate is per-eval **exact to ~±3%** and the coefficient scales with ANE program
shape, not with wall-clock: the S=32 kernel raises one ANE-lane event per ~2 evals
(0.5/eval), the S=160 unified kernel ~1/eval, the CoreML minilm program ~2.9/pred
(two ANE regions per prediction). M4 has no SOC-NI8/NI9 rows at all in this OS's
channel set — on M4 the equivalents were the `AMC Stats` byte counters
(`DCS RD` sums system-wide traffic here, ~1.9 GB/s even at idle, and is NOT ANE-specific:
do not read the `DCS_ANE_L0_RWR` column on M4 rows).

### 3. DCS floor states (free with the same dump)

During M5 bursts the `DCS Floor → ANE-DCS-BW` / `SOC Floor → ANE-LNK0/1-AF-BW`
tick lanes rise from their idle floor with the burst windows (ticks, duty-cycle
semantics — EXP-022/EXP-024 signal, not event counts). `AMCC RD/WR` (DCS BW) show
small event deltas tracking the AMCC master, unrelated to ANE evals. F1–F6
byte-level DCS lanes (M4-style) are not exported in the M5 PMP0 channel set.

## Verdict (C-67 gate form)

**Measured statement of what modulates the rate:** on M5 Max/27.0.1 the ANE
interrupt handler counters are closed at user level for direct-API *and* CoreML
(dual-control, 160k evals+120k predictions: zero) — no modulation exists to
measure; the working per-eval counters are `PMP0 SOC-NI Util BW → SOC-NI9 "ANEXL U"`
(and `SOC-NI8 "ANE UP"`) with shape-dependent coefficients 0.5/1.0/2.9 per eval,
reproducible ±3%. The per-eval interrupt counter is real hardware on M4 (1.46/eval
direct, matches MEASURE-012 CoreML band) and M5 gates its userland observation.
Honest bounds: these are whole-engine lane events (a per-eval proxy under a fixed
program), not per-task named counters; they attribute ANE activity, not which client
caused it when several clients share the engine — same caveat class as EXP-022.

## Files

- `pulse_table.tsv` — 18-run joined table (this dir).
- `raw/*.jsonl` — enginemon `silicon-ledger/1` streams (provenance header per file).
- `raw/*.work.log` — workload stdout with eval counts + ledger names.
