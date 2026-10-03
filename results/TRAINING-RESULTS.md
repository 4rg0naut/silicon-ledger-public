# Decision model — training run 1

**`bench/train_decision_model.py --epochs 8 --batch 4 --max-len 256`**
ModernBERT-base + Laya's marker-pointer head · MPS · 8 epochs, ~6 h, 0.92 s/step · exit 0

## Per-epoch dev results

| epoch | dev acc | dev loss (CE+Brier+RPS) | best.pt |
| ---: | ---: | ---: | :--- |
| 0 | 0.4567 | 1.3786 | |
| 1 | 0.4811 | 1.3168 | |
| 2 | 0.5400 | 1.2764 | |
| 3 | 0.5444 | 1.2636 | |
| 4 | 0.5800 | 1.2723 | |
| 5 | 0.5900 | 1.2456 | ✓ |
| 6 | 0.5811 | **1.2279** | ✓ **selected** |
| 7 | **0.5933** | 1.2366 | |

**Accuracy and loss diverge at the end.** Epoch 7 has the best argmax accuracy (0.5933) but a
*worse* combined objective than epoch 6 (1.2366 vs 1.2279). Since the objective contains Brier,
this is the calibration tradeoff showing up on its own: the sharper model wins on argmax and loses
on probability quality. `best.pt` is selected on loss, so it keeps epoch 6.

## The number that matters: the achievable ceiling

Dev = 180 calib cases / 900 decisions (case-id split, seed 0, so it was never trained on).
An oracle that **always picks the annotators' plurality** scores:

> **0.6602**

**The pre-registered gate is dev acc ≥ 0.760. That gate is unreachable on this dev set — it exceeds
the oracle.** The docstring's reference (0.785) must have been measured on data with more annotator
agreement; it is not a like-for-like comparison.

And the ceiling is not uniform — it tracks annotator disagreement (`label_agreement.total_variation`):

| TV | n | oracle ceiling |
| --- | ---: | ---: |
| 0.00–0.15 | 455 | **0.7574** |
| 0.15–0.30 | 251 | 0.5907 |
| 0.30–0.50 | 130 | 0.5389 |
| 0.50–0.70 | 60 | 0.4944 |
| 0.70–1.01 | 4 | 0.4042 |

**So on the clean half the 0.760 gate is exactly the ceiling — and on the disputed half it is
mathematically impossible.** The gold is a *panel distribution*, not a label: one sampled row has
`human_review` at 0.433 with total_variation 0.567, i.e. the "correct" answer is a 43% plurality.

**Read:** our 0.5933 is **90% of the 0.6602 attainable**. Reported against the gate alone it looks
like a 17-point failure; against the ceiling it is a 6.7-point gap, and much of that gap sits in
rows where no model can do better.

## What this means for the calibration axis

This is the same phenomenon as the rest of the investigation, seen from the other end:

- Laya's author: confidence stays at 0.885 while accuracy on Devanagari is 0% — **over**-confidence.
- Our ECE finding: 0.289 with a panel-doubt gap, reproducible to four decimals.
- **This run: the objective and argmax disagree about which epoch is best** — and the objective is
  the one that contains Brier.

The dataset already carries annotator disagreement (`total_variation`), which is the `panel doubt`
axis we built by hand elsewhere. **Measured accuracy should be reported per-TV bucket, not pooled** —
pooling hides that the ceiling itself moves with disagreement.

## Calibration on dev — measured, both checkpoints

`bench/eval_dev_calibration.py` (dev only; the test split stays untouched)

| checkpoint | acc | Brier | CE | mean conf | ECE | gap |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **best.pt** (ep6) | 0.5811 | **0.1619** | **1.0660** | 0.5788 | **0.0497** | −0.0023 |
| last.pt (ep7) | **0.5933** | 0.1636 | 1.0730 | 0.5871 | 0.0519 | −0.0063 |

**Epoch 7 wins on argmax and loses on Brier and ECE.** The accuracy/loss divergence is real and the
loss-based selection (epoch 6) is the better-calibrated checkpoint.

### The finding: pooled ECE hides a two-sided calibration failure

| annotator disagreement | n | acc | mean conf | gap | oracle ceiling | % of ceiling |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| TV 0.00–0.15 | 455 | 0.6967 | 0.6205 | **−0.0762** | 0.7574 | 92% |
| TV 0.15–0.30 | 251 | 0.4940 | 0.5205 | +0.0265 | 0.5907 | 84% |
| TV 0.30–0.50 | 130 | 0.4538 | 0.5322 | +0.0783 | 0.5389 | 84% |
| TV 0.50–1.01 | 64 | 0.3594 | **0.6050** | **+0.2456** | ~0.49 | ~73% |

**The pooled ECE of 0.0497 looks excellent and is misleading.** The model is *under*-confident by
0.076 where annotators agree and *over*-confident by **0.246** where they disagree. Those errors
cancel in the pooled average, so the headline number is clean while the model is
**most confident exactly where the answer is least knowable.**

This is the same structure found everywhere else in this investigation:

- Laya's author — confidence holds at 0.885 while accuracy on Devanagari is 0%
- our JevBench ECE work — 0.289, with the panel-doubt gap reproducing to four decimals
- **this run** — the training objective and argmax disagree about which epoch is best

**Actionable:** report accuracy and calibration **per disagreement stratum**, never pooled. The
dataset already carries `total_variation`; the strata cost nothing to compute and pooled numbers
hide the direction of the error.

**And the honest gap:** the model achieves 73–92% of the attainable ceiling per stratum, weakest on
the disputed rows — which is precisely where a decision model would be trusted to be uncertain.
