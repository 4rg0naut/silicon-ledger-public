# Layer selection — final state

## Selected

| layer | winner | how it was decided |
| --- | --- | --- |
| **verify** (claim + source → yes/partial/no) | **Von-1.0** | 70% exact vs LettuceDetect 62% vs ModernCE 8% (broken) — on 53 hand-labelled items, per-stratum |
| **retrieve** | Granite-Embedding-97M + reranker | already evaluated in EXP-007 / 008 / 010 / 011 / 012; not re-run |
| **decision** | Von-1.0 as a threshold gate | confidence is monotonic in accuracy; `conf ≥ 0.9` covers 66% at 85.7% |

## Deferred or dropped, with the reason

| layer | state | why |
| --- | --- | --- |
| **extract** | built and run, **not decided** | recall 0.30–0.34, but n=15 with ~2 gold terms each and non-domain labels. Label wording alone moves recall by 0.244, so the test currently measures the evaluator. GLiNER2.5 runs fine (38–88 ms); NuExtract3 and GLiNER-Relex untested. |
| **contradiction** | dropped | 17 known-contested pairs is too few to rank anything; `contradictionchecker` not downloaded. Testing this honestly needs a purpose-built set. |
| **parse** | dropped | our zoo ports already carry benchmark numbers (OvisOCR2 96.58 OmniDocBench, MinerU, Unlimited-OCR, GLM-OCR). Ranking new candidates (docling.rs, LightOnOCR-2, Chandra) needs a PDF → gold-text set that does not exist yet. |

## The five findings worth keeping

**1. A positive control caught a broken model.** ModernCE-large-nli scored 8%, and three trivial pairs
showed why: identical sentences read as `neutral`, a flat contradiction read as `entailment` at
0.997. Without the control it would have been filed as "weaker" rather than "broken", and the 8%
blamed on our passages. **A control is not optional.**

**2. Our own model beat the purpose-built community model.** Von-1.0 70% vs LettuceDetect v2 62%.
The community tool was built for exactly this task; ours was ported for something else. Small,
domain-adjacent and already in place can beat purpose-built.

**3. The hand-written `confidence` labels carry no signal — the model's confidence does.**

| | measured | documented | claimed |
| --- | ---: | ---: | ---: |
| agent labels, yes-rate | 70% | 76% | 100% | ← backwards, no signal
| Von confidence bin | 0.0–0.5 | 0.5–0.8 | 0.8–1.0 |
| actual accuracy | 25% | 29% | **81%** | ← monotonic

That contrast is the argument for the decision-model labeller, in one table.

**4. Zero-shot extraction is dominated by label wording.** Same model, passages and concept; recall
moved 0.111→0.356 on phrasing alone. Any evaluation that fixes one label set is measuring itself.

**5. Residency is not efficiency.** Von is fully ANE-resident (3 regions, 0 GPU, 0 CPU) and still
measures 105 ms/decision, because its NLI design needs **one pass per option**. Laya's native head
scores all options in one pass and is **29× faster**. The architecture decides the pass count; the
port cannot rescue it.

## What to do next, in order

1. **Grow the gold set.** 55 items is the reason the confidence result is suggestive rather than
   conclusive, and the reason the extraction test is undecidable. This is the bottleneck for
   everything.
2. **Re-express the verify task as a single-pass multi-option decision** and train it on the gold
   set. That is where the 29× is, and both halves already exist: Laya's native head is ported, and
   the training triples now exist.
3. **Fix the extraction test** with domain-native label vocabularies drawn from our own corpus, and
   run NuExtract3 and GLiNER-Relex before ranking anything.
4. **Fix the Von ANE harness path** (`aot_h16g_ane/` → `aot/`) so the ported model can be re-run
   without hitting the stale-path failure.

## Honest scope note

One layer was decided with confidence (verify), one was decided usefully (decision as a threshold),
one was built but is undecidable as designed (extract), and two were dropped for insufficient gold.
Naming winners on the last three would have manufactured results. The framework, the gold set and
the negative findings are the deliverables.