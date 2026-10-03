# Groundedness layer — candidate results

**Task:** given a claim and the source passage it cites, decide `yes` / `partial` / `no`.
**Gold:** 55 items, hand-labelled by reading each claim against its passage. 2 items labelled
`insufficient` (retrieval misses) are excluded from scoring — no candidate can be fairly graded on
them.

```
gold:  yes 40   partial 11   no 2   (insufficient 2, excluded)
```

## Results

| candidate | licence | exact 3-way | yes/not agreement | verdict |
| --- | --- | ---: | ---: | --- |
| **Von-1.0 (ours, already on the ANE)** | ours | **70%** | **75%** | **SELECTED** |
| LettuceDetect v2 (mmBERT-base) | Apache-2.0 | 62% | 66% | runner-up |
| ModernCE-large-nli | MIT | 8% | 25% | **rejected — fails its own control** |

### Von-1.0 — selected

A standard NLI cross-encoder (ModernBERT-Large, 790 MB): score each candidate answer as a hypothesis
against the passage as premise, take the entailment logit, argmax. Passes the positive control
cleanly where ModernCE fails it outright:

| premise | hypothesis | entailment | neutral | contradiction |
| --- | --- | ---: | ---: | ---: |
| The ANE has 16 cores. | The ANE has 16 cores. | **0.931** | 0.009 | 0.060 |
| The ANE has 16 cores. | The ANE has 64 cores. | 0.000 | 0.000 | **1.000** |
| The sky is blue. | Bananas are yellow. | 0.000 | **0.925** | 0.075 |

By gold verdict: `yes` 78% exact (31/40), `partial` 55% (6/11), `no` 0% (0/2 — it answers `partial`
where I judged unsupported, i.e. it is over-generous on refutation).

**It is ours, and it is already at full ANE residency** (EXP-016: 3 regions, 0 GPU, 0 CPU). The
optimisation step for this layer therefore costs nothing — the winner is already on the chip.

### LettuceDetect v2 — runner-up

Behaviour by gold verdict (exact match):

| gold | n | exact | rate |
| --- | ---: | ---: | ---: |
| yes | 40 | 26 | 65% |
| partial | 11 | 6 | 55% |
| no | 2 | 1 | 50% |

It spreads across all three answers and does not collapse. Constructed as
`tokenize(passage, claim)` with `truncation="only_first"`, which guarantees the **claim** is never
truncated however long the passage is — an important property, and not the default.

### ModernCE-large-nli — rejected, and the reason matters

It never predicted `entailment` once in 53 items. A positive control explains why:

| premise | hypothesis | entailment | neutral | contradiction |
| --- | --- | ---: | ---: | ---: |
| The ANE has 16 cores. | The ANE has 16 cores. | 0.012 | **0.941** | 0.048 |
| The ANE has 16 cores. | The ANE has 64 cores. | **0.997** | 0.002 | 0.001 |
| The sky is blue. | Bananas are yellow. | **0.980** | 0.001 | 0.019 |

Identical sentences read as `neutral`; a direct contradiction reads as `entailment`. One index fires
for both contradictions and unrelated pairs, so **no relabelling produces a coherent NLI**. The
published `id2label` does not match the model's behaviour.

**This is the trap the LettuceDetect authors documented** — off-the-shelf groundedness and NLI
models scoring near chance on technical content — and it is worse than near chance here.

**Lesson recorded:** a positive control is not optional. Without the three trivial pairs above this
would have been reported as "a weaker candidate" rather than "a broken one", and the 8% would have
been blamed on our passages.

## What this means for the corpus

**70% is the best available and it is not good enough to auto-validate.** Nearly a third of verdicts
are wrong, so:

- Von is usable as a **triage filter** — its `no` and low-confidence verdicts are worth a human look
- it is **not** usable as an automatic gate that admits records into the corpus
- human review stays in the loop for anything that matters

That is a real result, not a disappointment: it tells us the layer needs either a domain-tuned
model (trainable — this gold set is now its training data) or continued human review. It also
justifies the ANE work later: a domain-tuned encoder this small would run essentially free.

## Still to do on this layer

- ~~run Von-1.0~~ — done, and it won
- locate the **TinyLettuce** checkpoints (the repo names I tried do not exist)
- if Von-1.0 also underperforms, fine-tune LettuceDetect or Von on this gold set and re-measure —
  55 items is small for training, so grow the gold set first
