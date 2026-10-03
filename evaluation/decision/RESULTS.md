# Decision layer — Von-1.0 as a validator

**Task:** claim + source passage → `yes` / `partial` / `no`. This is the decision-model job in our
pipeline, and Von-1.0 is the candidate that won the groundedness layer.

**Gold:** the 55 hand-labelled items; the 2 `insufficient` ones are excluded → 53 scored.

## Accuracy

```
exact 3-way match : 0.698
mean confidence   : 0.881
gap               : +0.183   (over-confident, as this model class always is)
```

## The confidence is informative — which is the point

| confidence bin | n | accuracy | mean confidence |
| --- | ---: | ---: | ---: |
| 0.0 – 0.5 | 4 | 0.250 | 0.448 |
| 0.5 – 0.8 | 7 | 0.286 | 0.652 |
| 0.8 – 1.0 | 42 | **0.810** | 0.960 |

**Accuracy rises monotonically with confidence.** That is exactly what the hand-written `confidence`
labels in the knowledge base failed to do — those scored 100% on `claimed` and 70% on `measured`, i.e.
no signal at all. Here the confidence carries real information.

## The operating point

| accept if | coverage | accuracy on accepted | human review |
| --- | ---: | ---: | ---: |
| conf ≥ 0.5 | 92% | 0.735 | 8% |
| conf ≥ 0.7 | 81% | 0.791 | 19% |
| **conf ≥ 0.9** | **66%** | **0.857** | **34%** |

**Recommendation: use `conf ≥ 0.9` as a triage gate.** Two thirds of claims are auto-checked at
~86% accuracy; the remaining third goes to a human. That is a real labour saving and it is honest
about the part it cannot do.

**Do not use it as a binary pass/fail.** 14% of its high-confidence verdicts are still wrong, and on
this layer a wrong "supported" is worse than no answer — it admits an unverified claim into the
corpus.

## Note on the two items it is worst at

Both of my `no` items came back `partial` — the model is over-generous on refutation. So its
*rejections* are more trustworthy than its *acceptances*, and a corpus gate should be tuned
conservatively on that side.

## Method note

An earlier run of this same analysis reported accuracy 0.000. That was a bug in the analysis script —
it compared Von's raw NLI labels (`neutral`) against my verdict space (`yes`) without the mapping.
The direction of the error was caught before it was reported, but it is recorded here because a
silent version of the same mistake is exactly the class of bug that produces a confident wrong
number.
