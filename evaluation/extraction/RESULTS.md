# Extraction layer — results

**Task tested:** given a source passage, does the extractor surface the technical facts in it?
**Gold:** derived mechanically — the technical tokens present in **both** a claim and its passage
(so neither side can game it). 15 of 55 items had any such token; mean 2.1 gold terms per item.

## The headline finding: label wording is the dominant variable

```
recall across ALL phrasings:  min 0.111   max 0.356
=> label wording alone moves the result by 0.244 recall
```

Same model, same passages, same concept — only the label phrase changed:

| concept | best phrasing | recall | worst phrasing | recall | spread |
| --- | --- | ---: | --- | ---: | ---: |
| API name | `framework class` | 0.267 | `method selector` | 0.111 | **+0.156** |
| value | `numeric value` | 0.244 | `measurement` | 0.133 | +0.111 |
| technical identifier | `code identifier` | 0.322 | `symbol name` | 0.267 | +0.056 |
| hardware | `processor` | 0.356 | `chip` | 0.322 | +0.033 |

**This is why the first probe looked like a model failure.** An initial test with the phrase
`"register field"` returned 1 of 7 named register parts. That measured the phrase, not the model.
Any evaluation of a zero-shot extractor that fixes one label set is measuring the evaluator.

## Checkpoint comparison (best phrasing per concept)

| checkpoint | mean recall | per concept | median latency |
| --- | ---: | --- | ---: |
| `gliner2.5-small-v1` (74M) | 0.297 | 0.322 / 0.267 / 0.244 / 0.356 | **38 ms** |
| `gliner2.5-base-v1` (194M) | **0.344** | 0.444 / 0.378 / 0.333 / 0.222 | 88 ms |

Base wins on 3 of 4 concepts and loses on hardware. Both are fast. Both are **low**.

## Honest verdict: this layer cannot be ranked yet

The measured recall is 0.30–0.34 — but **the test is the limiting factor, not the model**, and
saying otherwise would be unsupportable:

- **n = 15 items**, ~2 gold terms each. One hit moves recall by ~0.5. The numbers are too coarse to
  separate candidates meaningfully.
- **The gold is derived, not authored.** A "miss" may be the extractor finding a different-but-valid
  span, which this metric counts as nothing.
- **The label vocabulary is still not domain-native.** `register`, `opcode`, `selector`, `constant`
  and `instruction` — the words our sources actually use — were never tried.
- **Only one model was tested.** NuExtract3 and GLiNER-Relex remain unrun.

**So: not selected, not rejected — deferred pending a better test.** Recording a winner here would be
manufacturing a result.

## What was established

1. **GLiNER2.5 runs locally** via `gliner2 2.0.0` + `BoundaryExtractor` — 38–88 ms per passage.
2. **Label wording dominates** — measured, +0.244 recall from phrasing alone.
3. **`gliner2` ships training and LoRA tooling** — the API surface includes `TrainingDataset`,
   `apply_lora_to_model`, `load_lora_adapter`, `save_lora_adapter`. So domain adaptation is
   available, and this model can enter the same flywheel as Von: hand-label, fine-tune, re-measure.
4. **Gate findings** recorded separately in `GATE-NOTES.md` — the `gliner`/`gliner2` split, the
   transformers 5 `max_width` break, the undeclared `peft` dependency, the real call signature.

## To make this layer decidable

1. grow the sample to all 55 items and add more sources
2. use **domain-native label vocabularies**, built from the terms our own corpus contains, and
   report the best phrasing per concept — never a single fixed label set
3. run **NuExtract3** and **GLiNER-Relex** (the triple extractor) for comparison
4. if recall stays low, fine-tune via the shipped LoRA path and re-measure — Apache-2.0 permits it