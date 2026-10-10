# silicon-ledger — what the Neural Engine in your Mac actually does

A home lab, two Macs, one obsession: the **Neural Engine** (ANE) — Apple's
built-in AI chip that almost no software actually uses. We measured it,
broke it, fixed it, and wrote down every number, including the embarrassing
ones. Nothing here is a vendor claim.

## What's new (2026-10-10)

Latest round, with an honest **new vs already-public** verdict on each — full detail and
evidence in [**WHATSNEW.md**](WHATSNEW.md):

- **ANE activity, finally measurable** — the unprivileged IOReport counter `PMP0/SOC-NI9
  "ANEXL U"` is *lane-exclusive*: zero unless the Neural Engine is working, ~19.6k when it is
  (calibrated against matched idle/GPU/CPU runs). **New** as a discriminator.
- **Apple's hidden AI cache decoded** — the `~/Library/Caches/coreai-cache` layout and its key
  derivation (`modelHash` per model; `optsHash` a pure function of the compute-unit options).
  **New**.
- **The compiled plan is readable** — the cached `mpsgraph` bytecode printed as real MLIR: the
  op graph, `mps.aneArch`, and every ANE/GPU region function with its signature. **New** technique
  (that the format is MLIR is already public; the private dialects and the printing method are not).
- **Which architecture your Mac actually targets** — measured `h17c` (M5 Max) vs `h16g` (M4
  mini); a correction to a published ANE table is filed upstream
  ([issue](https://github.com/sbryngelson/ane-guide/issues/1)). **Extends** published work.
- **Apple's Foundation Model on the ANE, measured unprivileged** — `ANEXL U` reads 0 at idle and
  10,862 across an `fm` burst; no GPU engagement above idle.
- **The ANE↔GPU link carries data, both ways** — a GPU kernel writes an IOSurface and signals,
  the ANE-side wrapper waits, content verified every iteration (~123/136 µs, 500/500).
  **New** (the wire is driven end-to-end; attaching a live ANE program is still blocked).

### The GPU side (round 2)

The M5 also has **Neural Accelerators inside its GPU cores** — one per core. We measured them
against everything else, and filed the results with the same honesty labels:

- **GPU vs the shader path** — the tensor path (`matmul2d`) is **2.26× faster than the hand-written
  shader kernel at 4096² and uses ~2× less GPU energy** for the same work; at decode (M=1) all GPU
  datapaths collapse to the same number, i.e. the tensor units buy nothing there. **New.**
- **GPU vs the Neural Engine on identical GEMMs** — the GPU wins **5–10×**, including at decode;
  and a plain matmul *does* reach the ANE at 2048³, while the 1×1-conv form of the same GEMM is
  2.1× slower there. **New** (measured); that the ANE prefers conv shapes is **known**.
- **A correction worth knowing** — the widespread "M5 multi-tile `matmul2d` silently no-ops, Apple's
  compiler bug" is **refuted on this box**: third-party MetalHLO runs 8/8 GEMMs correct including
  4096×4096. Our own earlier no-op was a *usage* artifact.
- **Why joules lie here** — GPU idle power swings **25→104 mW inside 30 s**, and this machine's only
  "display" is the screenshot-sharing **virtual display** (the headless floor is ≈0–3 mW). Both are
  measured in [QUIET-STATE](results/EXP-029-nax-crosslane/results/QUIET-STATE.md).

Details: [NAX activation and memory](results/EXP-029-nax-crosslane/docs/NAX-ACTIVATION-AND-MEMORY.md) ·
[the lane matrix](results/EXP-029-nax-crosslane/results/NAX-LANE-MATRIX.md) ·
[the tooling inventory](results/EXP-029-nax-crosslane/docs/TOOLING-INVENTORY.md).

## How to use this repo
Three layers, by what you came for:

1. **Front door** (5 minutes) — this page, [**WHATSNEW.md**](WHATSNEW.md) (findings with a
   NEW/EXT/KNOWN verdict each), and [PUBLIC-INDEX.md](PUBLIC-INDEX.md) (every experiment in plain words).
2. **Reusable instruments** — [`bench/`](bench/) (identity probe, power A/B, latency protocol),
   [`tools/`](tools/) (the `enginemon` engine monitor, the instrument registry), [`schemas/`](schemas/),
   and [`CROSS-REPO-CONTRACT.md`](CROSS-REPO-CONTRACT.md) for the join with the benchmark repo.
3. **Receipts** (verification, deliberately verbose) — [`PUBLIC-OPENCLAIMS.md`](PUBLIC-OPENCLAIMS.md),
   `knowledge/ane/` (the knowledge base *and* its machine-checkable records), and the raw evidence
   under `results/`. Read this layer when you want to verify, not to browse.

[**PUBLISH-POLICY.md**](PUBLISH-POLICY.md) states exactly what is published, what is private by
design (harness sources, gzipped raw captures, private clones), and why a prose mention of a private
path is a pointer, not a broken reference.

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
- `results/EXP-001..029` — the experiment records, one folder each. `PUBLIC-INDEX.md` maps them in plain words.
- `results/LADDER.md` — the five-rung summary: silicon ceiling → official overhead → port fidelity → task quality → energy.
- `results/FLEET.md` — which tool runs on which machine (and honestly, which don't).
- `MINEFIELD.md` — 18 lessons from everything that broke. Read this before debugging.
- `PUBLIC-OPENCLAIMS.md` — how our claims are recorded with receipts, and how you can verify them yourself.
- `knowledge/ane/` — the reverse-engineering knowledge base behind all of it.
- `tools/TOOLS.md` — the instrument registry: which tool is *the* one for a job (timing, joules, lane activity…).

## The house rules

1. Never re-run what is already recorded.
2. Every result carries its exact commands and its caveats.
3. Raw artifacts are preserved, never edited.
4. A number with no source is written as an em-dash, never guessed.
