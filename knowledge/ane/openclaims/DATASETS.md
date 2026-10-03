# Datasets for testing claim verification

**Question asked:** are there datasets built around OpenClaims we could test with?

**Answer: no.** OpenClaims ships no datasets — only conformance cases (4 valid, 5 invalid lifecycle
fixtures), 4 valid + 5 invalid event fixtures, CloudEvents and JSON-LD exemplars, and one demo corpus
(a versioned travel policy). Nothing usable as gold data.

**But that does not matter, because the spine is only a format.** Any public claim-verification
dataset can be converted into `claim.emitted` + `claim.verified` events. So the search moved to
datasets that would survive that conversion.

---

## The ranking

### 1. WiCE — **start here**

| | |
| --- | --- |
| **Verdicts** | `supported` / `partially_supported` / `not_supported` |
| **Evidence** | **sentence indices *and* token-level spans** |
| Licence | **CC BY-SA 4.0** |
| Access | direct download, plus a HuggingFace mirror (`tasksource/wice`) |
| Size | 1K–10K instances |

**Why it wins:** the verdict set is a *one-to-one match* to our spine's `support_type`:

```
supported            -> supports_directly
partially_supported  -> supports_partially
not_supported        -> contradicts
```

And the evidence is already **span-level**, so it converts into `Selector: text_span` with no
inference. This is as close to pre-formatted for our spine as a dataset could be.

- repo https://github.com/ryokamoi/wice
- paper https://arxiv.org/abs/2303.01432 (EMNLP 2023)
- mirror https://huggingface.co/datasets/tasksource/wice

### 2. HealthFC — clean mapping, two problems

750 English/German health claims. Labels `Supported` / `Not enough information` / `Refuted` map
directly, with up to five evidence sentences per claim.

**But:** only 750 claims, and **CC BY-NC-ND 4.0** — NoDerivatives. We could test on it, but we could
not publish a converted derivative. For a corpus we intend to share, that is disqualifying as a
foundation; usable as a held-out check.

### 3. FEVER and SciFact — large and span-annotated

- **FEVER**: 185,445 claims, `SUPPORTS`/`REFUTES`/`NOT ENOUGH INFO`, evidence is
  `[Wikipedia URL, sentence ID]` tuples. CC BY-SA 3.0 / GPL.
- **SciFact**: 1.4K expert claims, `SUPPORT`/`CONTRADICT`, evidence as sentence indices into
  abstracts. CC BY-NC 2.0.

Both are big and sentence-level, but the provenance is artificial (Wikipedia, or abstracts rather
than full papers) and the label sets are binary in SciFact's case. Good for volume, weaker for
realism.

### 4. AVeriTeC — realistic but the wrong shape

4,568 real-world claims with a 4-way label set (`Supported` / `Refuted` / `Not Enough Evidence` /
`Conflicting Evidence-Cherry-picking`). Human-annotated with reported inter-annotator agreement
(κ=0.619) — genuinely rigorous.

**But evidence is URL and QA-pair based with NO offsets.** No spans means no `Selector`, which
removes the main thing we need. Usable for verdict training, not for evidence grounding.

### Rejected

| dataset | why |
| --- | --- |
| **CLAIM_BENCH** | ~300 claim-evidence pairs from AI papers, but **extraction and validation only — no supported/contradicted verdicts** |
| **NewsClaims** | claim *detection* with attributes; no veracity label |
| **HaluEval**, generic HF uploads | no supported/contradicted verdict — often just "hallucinated or not" |
| **PUBHEALTH** | 11.8K claims but evidence is **document-level**, no spans |
| **Climate-FEVER** | licence unknown |

### Also found

- **RAGTruth** (~18k responses, word-level hallucination spans with **true character offsets**, MIT) —
  not verdicts, so it does not fit this layer, but the *offsets* make it useful for testing evidence
  selection.
- **The ACL Findings 2025 survey** (https://aclanthology.org/2025.findings-emnlp.1170) catalogues 65
  claim-verification corpora with size, modality, language, label class and justification type in
  Tables 9–12. **That is the master list to mine next** when WiCE is exhausted.

---

## What this changes

We hand-labelled **55 items** in this session. That was the bottleneck on everything downstream — too
few to make the confidence result conclusive, and the reason the extraction layer could not be
decided.

**WiCE gives us thousands, already in our verdict space and already span-annotated.**

Concretely:

1. Convert WiCE → `claim.emitted` + `claim.verified` events with `verification_method: human_review`
   (the labels are human-annotated), each with a real `text_span` selector.
2. **Keep our 55 items held out and never train on them.** They are *our* domain — Apple's chip, our
   own sources. WiCE is Wikipedia-derived. A model that scores well on WiCE has not thereby proved
   anything about ANE documentation, and our 55 are the only items that test that.
3. Re-run Von and any candidate against both: WiCE for volume and statistics, our 55 for domain fit.
   A model that is good at one and bad at the other is telling us something useful.

**The licence matters:** WiCE is CC BY-SA 4.0, so a converted derivative must carry the same licence.
That is compatible with publishing the corpus, provided we attribute and share alike — which is what
`SOURCES.md` is for.
---

# WiCE results — Von-1.0 evaluated on 958 claims

**Run:** 2026-09-25 · `wice_von_eval.py` · 2,845 evidence chunks over 958 claims · max-over-chunks
(published protocol) · MPS · per-claim gold: supported 528, partially_supported 165, not_supported 265

## Primary metric — is the claim supported at all

```
accuracy 0.771    precision 0.965    recall 0.710    F1 0.818
TP 492   FN 201   FP 18   TN 247
```

**The precision/recall balance is the finding.** Precision 0.965 against recall 0.710 means Von is a
*conservative* validator: when it says supported it is right 96.5% of the time, and it misses 29% of
genuinely supported claims. **For a corpus gate that is the correct bias** — admitting an unverified
claim is worse than deferring a good one to human review.

## Per gold label

| gold | n | says entailment | entailment | neutral | contradiction |
| --- | ---: | ---: | ---: | ---: | ---: |
| `supported` | 528 | 83.7% | 442 | 43 | 43 |
| `partially_supported` | 165 | 30.3% | 50 | 54 | 61 |
| `not_supported` | 265 | 6.8% | 18 | 191 | 56 |

**Two things to read here.**

**The `not_supported` row validates a mapping decision we made by reasoning.** WiCE measures
entailment, so we mapped `not_supported` to `verification_result: inconclusive` rather than to
`contradicts` — because a claim can fail to be supported either because the source contradicts it
*or* because the source is silent. The model agrees: it answers **neutral 191 against contradiction
56** on exactly those rows. Mapping to `contradicts` would have mislabelled 191 of 265.

**Its weakness is partial support.** It calls only 30.3% of `partially_supported` claims entailed,
because it treats "the source says most of it" as not-entailed. That is defensible but conservative,
and it is the main source of the 201 false negatives.

## Calibration — monotonic, and it replicates

| confidence | n | accuracy |
| --- | ---: | ---: |
| 0.00–0.50 | 15 | 0.467 |
| 0.50–0.80 | 131 | 0.534 |
| 0.80–0.95 | 155 | 0.684 |
| **0.95–1.01** | **657** | **0.846** |

**Our 55-item run gave 66% coverage at 85.7% accuracy; WiCE gives 69% coverage at 84.6% on 657
claims.** The operating point reproduces at seventeen times the sample size, which is what a real
result looks like rather than a small-sample coincidence.

**Recommended gate: `confidence ≥ 0.95`.** It covers 69% of claims at 84.6% accuracy and routes the
remaining 31% to a human — and given the precision/recall balance those deferrals will mostly be
genuinely-supported claims we chose not to trust automatically, not errors.

## Caveats

- WiCE is Wikipedia and news prose. **Our domain is Apple silicon documentation.** This measures the
  *skill*, not the domain fit — the 55 hand-labelled items remain the only domain test we have.
- The `insufficient`/retrieval-miss case is not exercised here: WiCE's oracle chunks are short and
  curated by construction, so retrieval quality is deliberately removed from the measurement.
- Single machine, single run, no repeats.

---

# GLiNER2.5-Decide on WiCE — a negative result

**Run:** 2026-09-25 · `wice_gliner_eval.py` · same 958 claims, same max-over-chunks rule as Von ·
CPU batched (measured fastest) · 342 ms/item

## Head to head

| model | accuracy | precision | recall | F1 |
| --- | ---: | ---: | ---: | ---: |
| **Von-1.0** | **0.771** | **0.965** | 0.710 | **0.818** |
| GLiNER2.5-Decide | 0.665 | 0.716 | **0.890** | 0.794 |

## It barely discriminates the negative class

| gold | n | Von says supported | GLiNER2.5-Decide says supported |
| --- | ---: | ---: | ---: |
| `supported` | 528 | 83.7% | 88.4% |
| `partially_supported` | 165 | 30.3% | 90.9% |
| **`not_supported`** | **265** | **6.8%** | **92.5%** |

**It calls 92.5% of unsupported claims supported.** The two columns should fall away together as the
gold gets weaker; GLiNER2.5-Decide's stay flat around 90%.

## And its confidence carries no signal

| confidence | Von accuracy | GLiNER2.5-Decide accuracy |
| --- | ---: | ---: |
| 0.00–0.50 | 0.467 | 0.545 |
| 0.50–0.80 | 0.534 | 0.649 |
| 0.80–0.95 | 0.684 | 0.687 |
| 0.95–1.01 | **0.846** | **0.678** |

Von's is monotonic; this is flat and then *falls*. Whatever the 0.95+ band means for this model, it
is not "more likely to be right".

## Why this is probably not a fair fight

**GLiNER2.5-Decide is trained for operational decisions** — routing, triage, tool selection,
guardrails, intent. Its published 60.1% is on Fast Decisions, where its strongest areas are support
intent (75.3%) and banking intent (64.3%). **Entailment is not what it was built for**, and its own
model card says so: *"The model does not reason, explain, or answer open questions. It is a specialist
for operational decisions."*

Three aspects of our framing may also be ours rather than theirs:

1. we combine claim and passage into one text under headings, a structure it has not seen
2. we use WiCE's label names rather than a vocabulary tuned for the model
3. classification here routes through the **span-extraction** schema path, not a dedicated head

**So the result is: as-shipped, it is not a drop-in replacement for Von on groundedness.** Not "the
model is bad" — it is a capable model pointed at someone else's job.

## The port itself succeeded, and that is separate

| gate | status |
| --- | --- |
| **1** fp32 wrapper vs the model's internal path | **cos 1.00000000, max abs err 0.00e+00** |
| **3** Core AI convert | **OK** |
| AOT compile (h16g, ANE) | **OK**, 15.3 s, `gliner25-decide_256_128_8.h16g.aimodelc` |
| 2, 4 (decode parity, engine gate) | not yet run |

**A 435M DeBERTa-v3-large model now has a compiled ANE artifact built from our own re-authored graph.**
That is independent of whether this model wins the task.

An honest note on the process: an earlier version of the exporter patched DeBERTa-v3's attention to
decompose SDPA. That was wrong twice over — the architecture's attention is *disentangled*, not
standard, and the model itself reports `Encoder rejected attn_implementation='sdpa'; falling back to
'eager'`. The trap I applied was real for Llama-class models and simply does not exist here. **The
port template's note — "exports cleanly at a fixed shape, no rewrite" — was correct and I should have
trusted it.**

## What follows

**Fine-tune it.** Apache-2.0, LoRA tooling ships in `gliner2`, and we now hold **958 human-verified
WiCE verdicts plus 55 domain items** — a training set, not only a test set. The architecture is the
one we concluded we needed (one pass, all candidates); what is missing is training on *this* question.

**And measure the ANE latency before anything else.** 342 ms/item on CPU is the number to beat, and
it is the third independent reason this port was worth doing.
