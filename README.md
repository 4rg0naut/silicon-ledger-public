# silicon-ledger — what the Neural Engine in your Mac actually does

A home lab, two Macs, one obsession: the **Neural Engine** (ANE) — Apple's
built-in AI chip that almost no software actually uses. We measured it,
broke it, fixed it, and wrote down every number, including the embarrassing
ones. Nothing here is a vendor claim.

## Why this exists

Apple's own toolchains quietly route "AI" workloads to the GPU even when you
ask for the Neural Engine — and say nothing about it. We built small
instruments to catch that happening, then learned which graphs the ANE will
accept, and how much faster it is when it says yes.

The short version: the same model, re-authored by hand for the ANE, ran
**3× faster and used 5× less GPU power** than its out-of-the-box export.
And the official compile path still lands on the GPU — silently.

## Start here (5 minutes, any Apple Silicon Mac)

```sh
python3 bench/identity.py
# prints what machine you are on: chip, model, cores, OS — one line of JSON

cd bench && clang -O2 -o /tmp/ane-probe ane-probe.m -framework Foundation && /tmp/ane-probe | head
# asks Apple's private Neural Engine framework what it exposes on your machine
```

## What's in here

- `results/measurements.json` — every measurement ever taken, machine-checked (920 rows).
- `results/EXP-001..023` — the experiment records, one folder each. `PUBLIC-INDEX.md` maps them in plain words.
- `results/LADDER.md` — the five-rung summary: silicon ceiling → official overhead → port fidelity → task quality → energy.
- `results/FLEET.md` — which tool runs on which machine (and honestly, which don't).
- `MINEFIELD.md` — 18 lessons from everything that broke. Read this before debugging.
- `PUBLIC-OPENCLAIMS.md` — how our claims are recorded with receipts, and how you can verify them yourself.
- `knowledge/ane/` — the reverse-engineering knowledge base behind all of it.

## The house rules

1. Never re-run what is already recorded.
2. Every result carries its exact commands and its caveats.
3. Raw artifacts are preserved, never edited.
4. A number with no source is written as an em-dash, never guessed.
