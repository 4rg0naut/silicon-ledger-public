# silicon-ledger — every AI compute lane in Apple silicon, measured

A home lab, two Macs (an M5 Max and an M4 mini), one discipline: run the same
AI workloads on **every compute lane** — the Neural Engine (ANE), the GPU's
tensor units, the GPU's shader path, the CPU — and publish every number,
including the embarrassing ones, the silent detours, and the outright failures.
Nothing here is a vendor claim.

## The numbers first

Six rows off the front page, one per lane pair. Every cell links to the
experiment that produced it; every experiment names its measurement window and
its caveats. State you are reading: mixed — rows marked *loaded-window* are
declared upper bounds, certified-quiet re-takes are open.

| lane · surface | measured | receipt |
|---|---|---|
| ANE, hand-re-authored model vs its stock export | **83 vs 10,390 mW** GPU power — 125× less, *and* faster (4.00 vs 4.33 ms) | [EXP-005](results/EXP-005-ane-residency/README.md) |
| GPU tensor units (`matmul2d`) vs hand-written shader, same 4096² | **2.26× faster**, ~2× less GPU energy | [EXP-029 matrix](results/EXP-029-nax-crosslane/results/NAX-LANE-MATRIX.md) |
| GPU vs ANE, identical fp16 GEMMs (M=1 / 512 / 2048) | GPU wins **10.2× / 7.3× / 5.4×** — including decode | [EXP-029](results/EXP-029-nax-crosslane/docs/NAX-ACTIVATION-AND-MEMORY.md) |
| NAX tensor units, hand-written MSL, fp8 (loaded window) | **32.0 TF** @2048³, bit-exact 24/24; needs Metal 4.1 — measured | [EXP-037](results/EXP-037-fp8-nax/results/fp8_matrix-20261026T1356Z.tsv) |
| NAX, same harness, int8 (loaded window) | **55.2 TF** @4096³ = **1.74× the fp16/fp8 band**, bit-exact 16/16 | [EXP-037](results/EXP-037-fp8-nax/results/lane_matrix-20261026T1509Z.tsv) |
| NAX, same harness, fp32 — the first fp32 lane measurement here | **14.0 TF** @4096³, bit-exact 16/16 | [EXP-037](results/EXP-037-fp8-nax/results/lane_matrix-20261026T1509Z.tsv) |

The full per-lane reference — every lane this fleet has measured, by surface,
with window, metric convention and instrument per cell — is
[knowledge/ane/16 §Consolidated lane table v2](knowledge/ane/16-neural-accelerators.md#consolidated-lane-table-v2--every-lane-measured-on-this-fleet-by-surface-2026-10-26-v1-same-date-superseded).

## Five numbers that surprised us

1. **55.2 TF** — int8 on the GPU tensor units at 4096³, 1.74× the fp16/fp8
   band, bit-exact, from one small hand-written harness
   ([EXP-037](results/EXP-037-fp8-nax/results/lane_matrix-20261026T1509Z.tsv)).
   Narrower is not just smaller; on this silicon it is *faster*.
2. **0 vs 19,611** — a single unprivileged IOReport counter (`ANEXL U`) that
   reads zero unless the Neural Engine is working. The only honest way to see
   Apple's silent GPU-default routing
   ([EXP-027 calibration](results/EXP-027-nax/results/p27_anpos_promote.txt)).
3. **25 → 104 mW in 30 s** — GPU idle power swings that much while *nothing
   runs*; the headless floor is ≈0–3 mW. Without this, every joule on this
   page would be noise ([QUIET-STATE](results/EXP-029-nax-crosslane/results/QUIET-STATE.md)).
4. **83 vs 10,390 mW** — the same embedder, hand-re-authored for the ANE, at
   125× less GPU power and faster than its published GPU build
   ([EXP-005](results/EXP-005-ane-residency/README.md)).
5. **1.7–8.5× slower** — the *same* GEMMs routed through Apple's generic MSL
   lowering instead of the graph path; and via that path even fp4 buys nothing
   (≤ 1.3 TF vs 32–55 TF native). Where your work goes matters more than what
   it is
   ([raw diff](results/EXP-022-m5max-baseline/raw/1427z-bench-diff-vs-example.txt)).

## What's new

The current round, every finding labelled **NEW / extends-public / already-public**
with its evidence link, is [**WHATSNEW.md**](WHATSNEW.md) — that page carries
the dates; this one doesn't go stale.

## How to use this repo

Three layers, by what you came for:

1. **Front door** (5 minutes) — this page, [**WHATSNEW.md**](WHATSNEW.md), and
   [PUBLIC-INDEX.md](PUBLIC-INDEX.md) (every experiment in plain words).
2. **Reusable instruments** — [`bench/`](bench/) (identity probe, power A/B,
   latency protocol), [`tools/`](tools/) (the `enginemon` engine monitor, the
   instrument registry), [`schemas/`](schemas/), and
   [`CROSS-REPO-CONTRACT.md`](CROSS-REPO-CONTRACT.md) for the join with the
   benchmark repo.
3. **Receipts** (verification, deliberately verbose) —
   [`PUBLIC-OPENCLAIMS.md`](PUBLIC-OPENCLAIMS.md), `knowledge/ane/` (the
   knowledge base *and* its machine-checkable records), and the evidence under
   `results/`. Read this layer when you want to verify, not to browse.

[**PUBLISH-POLICY.md**](PUBLISH-POLICY.md) states exactly what is published,
what is private by design (harness sources, gzipped raw captures, private
clones), and why a prose mention of a private path is a pointer, not a broken
reference.

## Why this exists

Apple's own toolchains quietly route "AI" workloads to the GPU even when you
ask for the Neural Engine — and say nothing about it. We built small
instruments to catch that happening, then learned which graphs the ANE will
accept, how much faster each lane is when it says yes, and how much the whole
picture costs in joules. Apple publishes none of this; we publish all of ours.

## Start here (5 minutes, any Apple Silicon Mac)

```sh
python3 bench/identity.py
# prints what machine you are on: chip, model, cores, OS — one line of JSON

cd bench && clang -O2 -o /tmp/ane-probe ane-probe.m -framework Foundation && /tmp/ane-probe | head
# asks Apple's private Neural Engine framework what it exposes on your machine
```

## What's in here

- `results/measurements.json` — every measurement ever taken, machine-checked (966 rows).
- `results/EXP-001..037` — the experiment records, one folder each. `PUBLIC-INDEX.md` maps them in plain words.
- `knowledge/ane/16-neural-accelerators.md` — the consolidated lane table: every lane measured on this fleet, by surface, single reference before any speed/energy comparison.
- `results/LADDER.md` — the five-rung summary: silicon ceiling → official overhead → port fidelity → task quality → energy.
- `results/FLEET.md` — which tool runs on which machine (and honestly, which don't).
- `MINEFIELD.md` — 18 lessons from everything that broke. Read this before debugging.
- `PUBLIC-OPENCLAIMS.md` — how our claims are recorded with receipts, and how you can verify them yourself.
- `tools/TOOLS.md` — the instrument registry: which tool is *the* one for a job (timing, joules, lane activity…).

## The family

- **[silicon-ledger-bench](https://github.com/4rg0naut/silicon-ledger-bench)** — the runnable side: burst-mode ANE/GPU/memory benchmark harnesses that emit the measurement rows this repo records. Run it yourself.
- **[memory-knowledge](https://github.com/4rg0naut/memory-knowledge)** — the claim-provenance infrastructure underneath: quote-gated capture, hash-chained ledger, the OpenClaims spine.
- **[ai-project-spine](https://github.com/4rg0naut/ai-project-spine)** — the one-file ledger gate, extracted, if you want the discipline without the lab.

## The house rules

1. Never re-run what is already recorded.
2. Every result carries its exact commands and its caveats.
3. Raw artifacts are preserved, never edited.
4. A number with no source is written as an em-dash, never guessed.
