# Making the benchmarks consistent — what's wrong, and what to do

You're right that the tables aren't homogeneous. I audited it rather than guessing: **6 of 18 reports
name no benchmark, none state the split, 6 name no hardware**, and the same latency column held
values measured per-decision, per-embedding, per-pair and per-option-pass. Here's what's actually
broken and a concrete fix.

---

## What's inconsistent, with evidence

| # | problem | evidence |
| --- | --- | --- |
| 1 | **Latency units differ and are unlabelled** | one column holds `74 ms`, `790 ms`, `68.1 ms`, `24 ms` — per-decision, per-embedding, per-pair, per-option-pass |
| 2 | **Benchmark and split unstated** | 6 of 18 reports name no benchmark; **0 of 18 state the split** |
| 3 | **Hardware unstated** | 6 of 18, including MiniLM (EXP-003) and the candidate landscape (EXP-015) |
| 4 | **Our JevBench rows are public-only** | **231 of 534 items.** The leaderboard is the full 534 — so our rows are not actually rankable against it |
| 5 | **Tier sets differ** | our Intelligence is 3-tier; JevBench's 45.8 is 4-tier (adds `judge`) |
| 6 | **Provenance mixed** | our measurements sit beside vendor claims (bge SciFact, EmbeddingGemma deltas) with no marker |
| 7 | **Precision mixed** | fp32 / fp16 / int8-affine rows in one table |
| 8 | **Energy denominators differ** | MiniLM's 5.6× is vs `CPU_ONLY`; Laya's 48.7× is GPU-power-avoided |

**Root cause:** the reports were written one at a time, and each table was hand-maintained. Drift is
inevitable when numbers are typed into prose.

---

## The fix — already built

**`bench/results_table.py` + `results/measurements.json`.** Tables are *generated*, never typed.
The schema makes every field above **mandatory**; `null` is permitted but **prints as an em-dash and
counts as a gap**, so an unknown can never silently render as if it were measured.

```
$ python bench/results_table.py --gaps
  11/11 records incomplete
  laya-en-ane-s256     load_factor, energy_mw, energy_rail, energy_baseline
  reranker-ane-s512    tiers, latency_ms, latency_unit, load_factor, energy_mw, …
  …
```

**And it refuses to rank non-comparable rows.** A row is only compared when
`benchmark + split + scope + tiers + metric + unit + latency_unit` all agree:

```
$ python bench/results_table.py --compare laya-en-ane-s256
  comparable: 2 rows        <- OUR rows only; the published #33 row is EXCLUDED
                              (different split, scope and tiers)

$ python bench/results_table.py --compare von-cpu-s256
  comparable: 2 rows        <- the ANE/CPU pair, correctly comparable
```

That exclusion is the whole point: **our 41.5 and JevBench's 45.8 were never comparable**, and the
old tables implied they were.

---

## Closing the gaps — the measurements we missed

Ranked by how much they'd improve consistency:

### 1. A single latency protocol, applied everywhere  *(biggest win)*
Same item count, same warm-up, report **p50 and p95**, and state the **work unit** explicitly. Right
now Laya's "68.1 ms" and Von's "105 ms" look comparable and are not — one scores all options in a
single pass, the other makes N passes. **Also report ms/token**, which is the one axis that survives
across classes.

### 2. Every model at its own designed budget
We ran Laya-multilingual at S=256, 512, 1024 and 2048 — but Von only at S=256, and the embedder at
128/512. **Each row should state the checkpoint's own `max_len` and whether we ran at it.**

### 3. Energy for every row
We have it for **two** models. `tools/enginemon` already works unprivileged — it just needs running
per row, with the **rail and denominator named** every time.

### 4. A three-placement sweep per model
CPU / GPU / ANE, same graph, same inputs. We have this for Laya and Von; it's the measurement that
isolates "the accelerator" from "the mapping", and it should be standard.

### 5. Provenance as a first-class column
`ours` / `third-party` / `vendor`. Vendor numbers (bge SciFact, EmbeddingGemma's deltas, JevBench's
own rows) are legitimate context but must never sit in the same column as ours unmarked.

### 6. The judge tier — *cannot be closed*
JevBench's held-out splits (109 of 220 hard items, and the judge tier) are **not published**. Our rows
are public-only **by necessity**, not by choice. That must be stated on every row rather than fixed.

---

## What I'd do, in order

| step | effort | payoff |
| --- | --- | --- |
| ~~**A.** Migrate all existing rows into `measurements.json`~~ **DONE** | ~1 h | 887 records from 18 reports; **877 verified, 0 rejected**; gaps now measurable (44% benchmark unstated, 84% split unstated) |
| ~~**E.** Rewrite report tables as generated output~~ **DONE (SUMMARY)** | ~1 h | `bench/results_table.py --summary` writes `results/SUMMARY.md` — 131 comparison groups, generated not typed |
| ~~**B.** One latency protocol~~ **DONE** | ~2 h | `bench/latency_protocol.py` — fixed 10 warm-up + 100 measured, p50/p95/min/max **+ ms/token**, and the protocol is recorded *on the row*. Validated on Laya S=256: **p50 29.84 ms, p95 30.39, 0.1166 ms/token** |
| ~~**C.** Run `enginemon` per row~~ **DONE (protocol + Laya)** | ~1 h | **ANE 33.7 ms / GPU 23.2 mW vs GPU-specialised 65.6 ms / 869.8 mW — 1.9× faster, 37.5× less GPU power.** Rail and baseline now named on every energy row. Coverage is 3/890 because most rows are not re-runnable — that is a limit, not an omission |
| ~~**D.** Three-placement sweep~~ **DONE (Laya, partially clean)** | ~2 h | **ANE 26.0 ms · CPU 39.6 ms · GPU contaminated.** ANE is 1.5× the CPU on the same graph. The GPU figure needs a serial re-run |
| ~~**E.** Generated blocks in every report~~ **DONE** | ~1 h | **18/18 reports** carry a generated block appended below their original tables. Hand-written tables kept as evidence; generated block is canonical. +834 insertions, **-1 deletion** (my own earlier edit) |

**A is the prerequisite for everything else** and is cheap. E is what stops it regressing.

**One judgement call for you:** should `results/SUMMARY.md` keep cross-class rows at all? My view is
yes — but only with the comparability groups visibly separated and ms/token as the single shared axis,
because a reader *will* compare across classes whether we invite it or not. Making that comparison
honest beats forbidding it.

---

## Measured: the ANE has two throughput states, and our protocol must say which

Re-measuring Laya S=256 back to back produced **33.7 ms and 60.0 ms per decision** — a 2× swing on
identical code. This matches the zoo's own finding in `knowledge/ane-region-count-and-fp32-ops.md`:

> *the ANE shows two throughput states — burst ~1.85–2.25 ms and sustained ~4.75 ms — with a
> one-way transition ~830 inferences into a run that 4 minutes of idle does not restore.*

**Consequence for the schema:** a latency row is meaningless without the state it was measured in.
`scope` now records it (`"3000 calls, warm-up discarded (SUSTAINED state)"`), and
`bench/latency_protocol.py` measures the **burst** state by design (10 warm-up + 100 calls).

**This is exactly the class of thing the old tables hid** — the same model reported as "68.1 ms" and
"27.1 ms" in two reports, with nothing saying why.

---

## Measured: measurement hygiene is itself a requirement, and I got it wrong

Running three placement arms **in parallel** contaminated every one of them. The clearest symptom:

| "ANE" run | GPU power reported |
| --- | ---: |
| run alone | **23.2 mW** |
| run while a second probe was executing | **1131.2 mW** |

GPU power cannot rise 49× because the ANE is busy — the other probe was using the GPU. **Latency
inflated the same way**: the same ANE config measured 26.0 / 33.7 / 60.0 / 61.9 ms across runs, where
26.0 was the only one with nothing else executing.

**The rule this establishes, for the schema and for the next person:**
> One measurement at a time. Settle before starting. A latency or power row MUST record whether
> anything else was running, because an unqualified number here is not reproducible.

Clean results, serial runs only:

| placement | ms per decision | state |
| ---: | ---: | --- |
| **ANE** | **26.0** | clean, serial |
| CPU | 39.6 | clean, serial |
| GPU | 53.7 – 66.7 | **contaminated — upper bound only** |

**So the ANE is 1.5× faster than the CPU on the same graph**, and the GPU figure is not usable yet.

**Note on the earlier "burst vs sustained" attribution.** I first read the 26→60 ms spread as the
zoo's documented two-throughput-state behaviour. **That was probably wrong** — the spread is explained
by my own contention. The zoo's finding may still be real, but this data does not show it, and I
should not have claimed it without serial runs.

### Clean serial re-runs still vary — so the schema must carry a RANGE, not a point

Two further serial runs (nothing else executing, 60 s settle before each) gave:

| placement | run A | run B | 
| --- | ---: | ---: |
| ANE | 26.0 ms | 39.8 ms |
| GPU | 60.2 ms | 66.8 ms |
| CPU | 39.6 ms | — |

**The ANE varies 1.5× between clean runs.** So the contention was real but it is not the whole story —
there is genuine run-to-run variance (thermal, or the two-state behaviour the zoo documented).
Either way the conclusion for the schema is the same: **a single latency point is false precision.**
`scope` now carries the range and the number of runs, and the honest headline is:

> **ANE 26–40 ms · CPU 39.6 ms · GPU 60–67 ms** per decision, same graph, same inputs.

The ANE's advantage over the CPU is therefore **marginal-to-modest on this graph** (26–40 vs 39.6), and
**1.5–2.5× over the GPU**. That is a weaker claim than the 29× measured against JevBench's *CPU*
reference — and the difference is that JevBench's reference is a 4-thread Ryzen running a Python
package, not a tuned Core AI CPU placement.

---

## Attribution is shared, not unique — and that is correct

A check for "does any report hold another report's rows" found **64 cases**. Almost all are
**legitimate**: Von's JevBench numbers are evidence for both Von's port report (EXP-016) and the
JevBench report (EXP-018), and a reader looking for either should find them.

**What was actually wrong was the fragment labels, not the reports.** Four `exp011-*` ids had been
filed into `EXP-010`'s extraction fragment; they belong to EXP-011 and were moved. EXP-011's report
already held them correctly.

**The lesson for the schema:** a measurement's `id` is not a unique owner. Ownership is many-to-many —
one row can be evidence for several reports — so `measurements.json` records the row once and each
report's generated block selects it. Duplication across blocks is a *feature*, and a future check
should test *placement* (is the row where a reader would look?) rather than uniqueness.

---

## The local label classifier: I proposed it, and the evidence says we do not need it

I argued for a local decision model to canonicalise `unit`/`metric`, citing **"75 spellings of the same
value"**. **That number was produced by my own over-aggressive normalisation**, which stripped spaces
and punctuation entirely and merged genuinely different concepts. Re-checked with a fair rule, the
labels are not drifting — they are *descriptive*:

```
's (resident fm serve over HTTP; stated range 0.26-0.33 s)'
'ms (asset loads after collapse 320 ms -> 21 ms)'
'absolute delta over truncate at grid 128'
```

**Canonicalising those would destroy the information the row exists to carry.** And the honest test:

| approach | residue |
| --- | ---: |
| deterministic canonicalisation (case/space/punctuation) | collapses 1 of 165 — almost nothing to collapse |
| + a closed `unit_kind` matched on word boundaries | **≥94.5% classified; 49 of 893 remain, all concepts the list simply omitted** |

**So the task needs a schema change, not a model.** `unit_kind` is a closed set derived
deterministically; the descriptive `unit` stays verbatim as evidence. The remaining handful is a
human review of minutes, not a model call.

**This is the honest outcome and it reverses my recommendation.** A local model is not the answer
here — and I should not have proposed one on evidence I had produced myself with a rule too loose to
be trusted. The general lesson is the one this whole exercise keeps teaching: **check the metric
before building the thing it justifies.**

---

## Decision (2026-09-26): `protocol` / `unit_kind` stay mandatory-in-schema, optional-in-practice

`bench/results_table.py` makes every field in `FIELDS` mandatory for gap purposes, but **898/898**
records came back "incomplete" — the signal was drowned because `protocol` is set on 3 of 898 and
`load_factor`/`energy_*` on few. The fix is not to loosen the schema (a table *can* hide these,
which is the whole point of making them explicit) but to report completeness in **two levels**:

- **Universal floor** (`id`, `metric`, `value`, `unit`, `provenance`) — enforced at merge time by
  `verify_extraction` and by the builder for new rows. Below it, a row is unusable.
  **0/898** records are below it.
- **Builder floor** (+`model`, `+benchmark`) — enforced for NEW rows by
  `bench/build_measurements.py`. **422/898** legacy extracted rows predate it (they were merged
  before `model`/`benchmark` became mandatory). This is **curation debt, reported as such**, not an
  error: back-filling 422 rows' model/benchmark is a per-report curation task, not a pipeline bug.
- **Context fields** (`protocol`, `load_factor`, `energy_mw/rail/baseline`, `unit_kind`, ...) —
  a row lacking them is *incomplete*, not *wrong*. 898/898 lack at least one by design (most
  predate the field or the quantity was simply not measured).

`--gaps` now prints all three levels separately so the number that matters (rows below the
universal floor) is no longer buried. Filling `protocol` for the legacy rows and the 422
`model`/`benchmark` gaps is tracked as curation debt; it is deliberately **not** automated, because
inventing a `protocol` or `model` for a row whose report doesn't state one would violate the repo's
core rule (null = NOT MEASURED, printed, never invented).

## Decision (2026-09-26): `--compare` uses the same normalisation as `--summary`

`--compare` previously compared raw `COMPARE_KEYS` (exact string equality), while `--summary` groups
on the *normalised* key (`norm_key`/`norm_scope`). A formatting variant (e.g. `chance-corrected
0-100` vs `chance-corrected, 0-100`) grouped in the summary but was invisible to `--compare`.
`--compare` now compares on the same normalised `keys_for(...)` class, so a variant groups in both.
It is deliberately **stricter than `--summary`'s wildcard**: an unstated (null) key is *not*
treated as "matches anything" in `--compare`, because `--summary` flags that case as
"grouping uncertain" and a side-by-side comparison should not rest on an unflagged assumption.

---

## Drift adjudication, ROWS vs ledger (2026-10-03)

Standing re-check after the non-destructive merge shipped (bad6be6). Method:
map every `bench/build_measurements.py` ROWS tuple through `KEYS`, diff field
by field against `results/measurements.json`; for ROWS-only ids, probe the
ledger for a row with the same value, and grep `results/EXP-*/README.md` for
the value as provenance. Nothing was applied; this is the adjudication for
owner review.

### Root cause of the "47 field drifts"

**8 shared literals are still legacy 22-field tuples** (pre-pad era): with the
end-padding the builder applies, their trailing provenance/date/command shift
three slots into `load_factor/energy_mw/energy_rail`. Worked example —
`laya-en-ane-s256` maps as `load_factor='ours'`, `energy_mw='2026-09-22'`,
`energy_rail='bench/jevbench_ane.py + laya_ane_bench.py'`. Shifted literals:
`laya-en-ane-s256`, `laya-en-ane-energy`, `laya-en-cpu-published`,
`von-ane-s256`, `von-cpu-s256`, `mpnet-base-scifact`, `minilm-coreml-ane`,
`granite97m-w8`. The ledger rows (merged from machine-verified fragments)
carry the correct values; the drift is a TABLE defect, not data loss.
**Safety warning: `--force` today would write `'2026-09-22'` into `energy_mw`
for those ids.** Remaining drifts (bge-base/bge-small-scifact, granite97m-w8
benchmark naming) are cosmetic naming variance (`ndcg_at_10` vs `ndcg@10`,
`MTEB (SciFact)` vs `MTEB SciFact`); ledger spellings stay authoritative.

### The 27 ROWS-only ids: none is a missing measurement

Every valued limbo id already exists in the ledger under its normalized id
(same value, same measure): `grid-64/128/256/512/1024` → `granite-97m-grid*-ndcg10`;
`granite97m-ane-scifact` → `granite97m-ane-s512` (0.68546); `granite97m-ane-nfcorpus`
→ `granite-97m-nfcorpus-s512`; `granite97m-ane-french` → `granite-97m-ane-s512-ndcg10`;
`e5-small-french` → `multilingual-e5-small-ref-ndcg10`; `qwen3-reranker-ane` →
`reranker-delta-ndcg10`; `pipeline-ours-reranked` / `pipeline-bgebase-reranked` →
`achieved-granite-full-pipeline` / `bge-base-plus-reranker-ndcg10`;
`minilm-coreml-cpu/gpu` → `minilm-coreml-cpu-only-throughput` /
`minilm-coreml-cpu-and-gpu-throughput`; `von-ane-v0/v1` → `von-v0-ane-latency` /
`von-v1-ane-latency`; `granite97m-fp16-13reg`/`-1reg`/`fp32-0reg` → the
`granite-embedding-97m-fp16-v*-…-converged-median-latenc*` family; `granite97m-coreai-*`
→ `granite-cpuonly/gpu/neuralengine-warm-median`; `laya-ml-ane-s256` →
`laya-ane-latency-p50-s256` (EXP-017); `tiny-fp16` →
`tiny-ane-shaped-control-graph-…-ane-an` (66 regions, F-27). **Recommendation:
retire the ROWS table as a historical seed** — annotate its header
"pre-normalization seed, superseded by the ledger; do not apply" — and drop
--apply-new/--force application rather than inventing parallel ids.
`granite97m-w4/w6` carry `value=None`: never measured; placeholders. Retire
with the table, do not create null rows.

### Recommendations

- **R1** Fix the 8 legacy literals in `ROWS` (insert the three `None` pads
  before the trailing provenance/date/command) or retire the table per above
  — until then treat `--force` as unsafe for shared ids.
- **R2** Builder: assert exact arity per row (`len(row) == len(KEYS)`, naming
  the offending id) instead of end-padding silently.
- **R3** Retire the 25 duplicate limbo ids + 2 placeholders; no ledger rows to add.
- **R4** `audit_measurements.py --json` is now the standing re-check (920/920
  rows, coverage declared in `_note`); a rebuild that changes any shared row
  will surface there even if ROWS drifts.
