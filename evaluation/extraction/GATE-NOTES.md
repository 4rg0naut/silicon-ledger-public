# Extraction layer — gate findings (before any scoring)

Recorded because every one of these would have wasted an hour for the next person.

## Environment incompatibilities found

| finding | detail |
| --- | --- |
| **`gliner` ≠ `gliner2`** | `gliner 0.2.29` cannot read a GLiNER2.5 checkpoint — it looks for `gliner_config.json`, while 2.5 ships `config.json` + `encoder_config/`. `gliner2 2.0.0` was already installed and is the correct package. |
| **`transformers 5.16.1` breaks the default span path** | `SpanExtractor.from_pretrained` fails with `'ExtractorConfig' object has no attribute 'max_width'`. Loading emits *"You are using a model of type `extractor` to instantiate a model of type ``"*. |
| **`BoundaryExtractor` still works** | The 2.5 checkpoint loads and runs fine through `BoundaryExtractor.from_pretrained`. So the failure is in one code path, not the model. |
| **`peft` is an undeclared dependency** | Import fails with `ModuleNotFoundError: No module named 'peft'` until it is installed. |

**Do not "fix" this by downgrading transformers.** Our working stack (torch 2.13, coremltools 9,
the ANE export path) depends on it. Use `BoundaryExtractor`, or a separate venv for gliner2.

## The API is not what the documentation implies

```
BoundaryExtractor.extract(text: str, schema, threshold: float = 0.5,
                          format_results=True, include_confidence=False,
                          include_spans=False, max_len=None, overlap_policy=None) -> Dict
```

**`text` is a single string, `schema` a single schema object.** Passing a list of entity names as
`schema` fails with `ValueError: Schema count (5) != text count (1)` — it is counted as five
schemas. The working form is a dict:

```python
m.extract(passage, {"entities": ["chip", "api", "register field", "byte offset"]},
          include_confidence=True)
```

Verified: **75 ms** on a ~1.5 KB passage, returning char spans with per-span confidence.

## First quality observation (not yet a verdict)

On a passage that explicitly names seven register-map parts (`Header`, `KernelDMASrc`, `Common`,
`TileDMASrc`, `L2`, `NE`, `TileDMADst`), the small checkpoint returned **one** — `Header` at 0.54
confidence — for the label `"register field"`.

GLiNER is zero-shot but demonstrably sensitive to **label wording**, and `"register field"` is an
unusual phrase likely outside its training distribution. **So this measures my label choice as much
as the model**, and the real test must:

1. try several phrasings per concept and report the best, not the first
2. use label sets drawn from the domain's own vocabulary where possible
3. record *which* phrasing won, since that is itself a reusable finding

Scoring it as-is would have produced a false negative on a tool that may be fine.

## Candidates and their status

| candidate | licence | status |
| --- | --- | --- |
| **GLiNER2.5-small / -base** | Apache-2.0 | **runs** (BoundaryExtractor, 75 ms); quality untested with proper labels |
| NuExtract3 (4B) | Apache-2.0 | not yet tried; needs a download and an MLX or torch path |
| GLiNER-Relex-large | Apache-2.0 | not yet tried; emits (head, relation, tail) triples with offsets and scores |
| Outlines + MLX | — | relevant only for schema-constrained *generation*; different job |

## What the test set still needs

The extraction test is **not** "passage → our existing claims" — a claim is a proposition, while
these models return spans and triples. The honest test is:

> given a passage and a schema drawn from the domain, does the extractor recover the facts our
> records assert about that passage?

Building that needs a per-record schema, which is real work and should be done deliberately rather
than improvised. Doing it badly would rank the tools on my phrasing rather than on their ability.