# EXP-019 — The two-channel fix: a correctness head for our decision models

**Question.** `openJev-verdict-2.0` (2026-09-22, 149.6M) beats Laya's 421M on Laya's own suite and
names the mechanism: gold labels are **expert-panel distributions**, not 0/1, so *one vector cannot
answer both* "what does the panel believe" and "am I right". Their proof:

```
accuracy (0.7710) - mean distribution confidence (0.6197) = 0.1513 = reported ECE
```

Can that second channel be ported to our build?

**Answer: yes — measured, not projected. Accuracy unchanged, ECE cut 69%.**

**Run:** 2026-09-22 · macOS 27.0 · base M4 · Laya English 421M on the ANE

---

## Result

| | distribution only | **+ correctness head** |
| --- | ---: | ---: |
| accuracy | 110/231 | **110/231** (identical) |
| top-label ECE | 0.2893 | **0.0884** |
| JevBench calibration sub-axis (a) | 42.1 | **82.3** |
| JevBench Calibration (mean of a and b) | 42.1 | **62.2** |

**The ordering is untouched** — the channel rescales the top-label probability while preserving the
ranking, so accuracy is *identically* 110/231. Only the calibration moves.

**And their formula reproduces on our data:** `accuracy (0.476) − mean confidence (0.7655) = −0.2893`
= the reported ECE, to four decimals. Negative because our model is *under*-confident — the mirror of
their over-confident case, and the same phenomenon.

## What was built

**`CorrectnessChannel`** in `bench/jevbench_ane.py`, wired into `LayaANEAdapter.run`. When weights are
attached the adapter emits **both channels**:

```python
res.raw = {"channels": {"distribution": dist, "confidence": conf}}
```

and JevBench scores the rescaled distribution.

| | |
| --- | --- |
| features | top probability, top−2 margin, normalised entropy, log(option count), is-binary |
| model | logistic regression over 5 features — **no encoder retrain, no model at runtime** |
| fit | **out-of-fold** (leave-one-out on 231 items), so it never scores a decision it saw |
| cost | arithmetic on probabilities we already have — portable to the ANE as a tiny MLP |

**The head never sees the gold label** — only the *shape* of the prediction. That is what makes it a
genuine second channel rather than a leak.

## The cascade, which is the same idea

If the confidence channel is discriminative, the confident decisions can be accepted and the rest
escalated — the non-autoregressive analogue of what speculative decoding does with tokens:

| coverage | accuracy on accepted | escalated |
| ---: | ---: | ---: |
| 100% | 47.6% | 0% |
| 60% | 52.9% | 40% |
| 50% | 60.0% | 50% |
| **40%** | **67.4%** | 60% |

**AUROC 0.6579** (theirs: 0.7664). Discriminative enough to pay: accepting 40% and escalating 60%
lifts accuracy **47.6% → 67.4%, +19.8 points.**

**Speculative *decoding* does not apply to us** — it needs a token sequence to speculate on and our
models are non-autoregressive, one pass, no decode loop. **Its structure does**: skip the expensive
path where a cheap signal is already decisive.

## Caveats

- **The fidelity sub-axis is not computable from our runs.** JevBench's Calibration is the mean of
  (a) ECE and (b) *fidelity to the exact gold distribution*. Our runs emitted no distributions for the
  **10 `probability`-family items**, so (b) is held equal across both rows. **The 62.2 is a floor.**
- **`42.1` is not our published Calibration.** Our leaderboard row scored **62.5** on the full 534
  with the judge tier. This is the same quantity on 231 public items — comparable to itself
  before/after, not to the leaderboard.
- **231 items is small.** Leave-one-out means no leakage, but the interval is wide.
- **AUROC 0.66 < their 0.77.** Our head is weaker — fit on 231 rows, not a real calibration fold.
- **The cascade's "escalated" arm has no second model.** The gain assumes escalation is correct, which
  on JevBench's *hard* tier it would not be.
- **The leaderboard number needs all 534**, and JevBench's held-out half is unpublished.

## Why this matters more than the ANE work

| change | JevBench Score |
| --- | ---: |
| the ANE's entire speed win (+19.7 Speed points) | **+3.4** |
| this, if the floor holds | **+2.5** |

**Calibration is not capped.** Speed saturates at 0.1 s and Cost is priced by size class, so two of
JevBench's four axes are structurally closed to us. **Calibration and Intelligence are the two that
are not — and this is the first change all session that moves one of them.**

## Artifacts

- `bench/correctness_head.py` — features, fit, ECE, and the leave-one-out measurement
- `bench/calibration_axis.py` — JevBench's own `calibration()` applied to both channels
- `bench/jevbench_ane.py` — `CorrectnessChannel`, wired into the adapter
- `work/memory-stack/laya_ane_public.json` — the 231 decisions with full probability vectors
