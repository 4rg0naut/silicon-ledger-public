# ANE knowledge base — design

**Why this file exists:** the knowledge base is not just for us to read. It is intended to
eventually **feed a model we train** — as retrieval corpus, as fine-tuning data, and as an
evaluation set. That requirement changes how it must be shaped, so it is stated up front rather
than bolted on later.

---

## The problem with prose

Prose is for humans. A model needs:

- **atomic claims** — one fact per unit, so it can be learned, retrieved, and counted
- **provenance on every unit** — where did this come from, and how strong is it?
- **honest confidence** — so a guess is never trained as a fact
- **stable IDs** — so a claim can be tracked across revisions and deduplicated
- **scope limits** — "true on M3, not on M1" is part of the fact, not a footnote

Prose written now and converted later means reading everything twice, and the conversion will
drift from the prose. So we produce both **from the same pass, in the same file**.

---

## The two-layer design

Every document in this knowledge base has two layers, in one file:

```
knowledge/ane/05-gotchas.md
├── prose          ← for humans: narrative, reasoning, context, code
└── ```jsonl       ← for machines: one atomic claim per line, extractable
```

**Why in one file rather than two?** Because they are reviewed together, edited together, and
cannot drift apart. A script extracts every ```jsonl block into `records/*.jsonl` mechanically —
no model, no re-reading, no judgement. One source of truth, two renderings.

```
ane/
  00-DESIGN.md              this file
  01-landscape.md           ← prose + jsonl
  02-private-api.md         ← prose + jsonl
  03-program-format-and-compile.md
  04-runtime-and-memory.md
  05-gotchas.md
  06-measurement.md
  records/                  generated: extracted jsonl, validated
  SOURCES.md                every source with its license
```

---

## The record schema

One JSON object per line. Every field is required unless marked optional.

```json
{
  "id": "GOTCHAS-014",
  "claim": "The ANE kernel DMA prefetcher throttles to 17-19 GB/s when the per-core transfer is an exact multiple of 1 MiB.",
  "kind": "gotcha",
  "confidence": "measured",
  "source": "https://eiln.github.io/posts/ane-dma.html",
  "source_type": "primary",
  "retrieved": "2026-09-23",
  "topic": ["memory-bandwidth", "dma", "performance"],
  "entities": ["ANE", "M3"],
  "evidence": "D=2048 at 997.6 us vs D=2016 at 293.8 us; nominal 45-60 GB/s falls to 17.3 GB/s",
  "caveat": "M3 affected; M1 and M5 Max reportedly unaffected",
  "contested": false
}
```

| field | meaning |
| --- | --- |
| `id` | `<FILEDOC>-<NNN>`, stable, never reused |
| `claim` | **one self-contained sentence.** Must make sense with no surrounding context |
| `kind` | `fact` \| `definition` \| `procedure` \| `gotcha` \| `measurement` \| `open-question` |
| `confidence` | `measured` \| `documented` \| `inferred` \| `claimed` |
| `source` | URL or local path. **If there is no source, the claim is dropped** |
| `source_type` | `primary` \| `secondary` \| `our-own` |
| `retrieved` | date we read it |
| `topic` | tags for retrieval and curriculum |
| `entities` | chips, APIs, projects, models named |
| `evidence` | the numbers or facts that support it (optional) |
| `caveat` | the scope limit that makes it not-universally-true (optional) |
| `contested` | `true` when sources disagree — the dispute is part of the record |

---

## The rules that actually matter

**1. Confidence is not decoration — it is a training filter.**
A model trained on `claimed` as if it were `measured` learns to state speculation with
confidence. That is the exact failure we have been measuring all week in other people's models.
`confidence` and `caveat` exist so that a training pipeline can *exclude* them:

```
pretraining / RAG : everything
fine-tuning (SFT) : measured + documented + our-own
never             : claimed, presented without its label
```

**2. Every claim carries its source, or it does not enter.**
A record without provenance is unverifiable and untrainable. This also makes the corpus
self-auditing: any claim can be traced back and re-checked.

**3. One claim per record.**
Two facts in one sentence cannot be retrieved separately, counted, or de-duplicated. Split.

**4. `contested` is a feature, not a problem.**
Where sources disagree, both go in, both marked, and the disagreement is recorded. A model that
learns "X is disputed and here are both positions" is more useful than one that learned whichever
source we happened to read first.

**5. Never let our own findings hide among theirs.**
`source_type: "our-own"` separates what *we* measured from what we *read*. This matters for
honesty, and it matters for evaluation — see below.

---

## How it renders into uses

| use | how | status |
| --- | --- | --- |
| **RAG / retrieval** | `records/*.jsonl` + prose, embedded and indexed | works as soon as records exist |
| **Instruction tuning** | generate Q&A pairs *from* each record (claim → question) | derivable, not stored |
| **Continual pretraining** | the prose files verbatim | available now |
| **Evaluation set** | a held-out slice of records, never trained on | **requires discipline now** |
| **Sharing** | the whole `ane/` directory, prose + records | licence tracked per source |

### The held-out split — the one thing we must get right early

If the knowledge base becomes training data, it must also be able to **measure** whether the model
learned. That needs questions the model has never seen.

So: a slice of records is marked `holdout` **at creation time**, sealed, and never included in any
training run. Retroactively carving out a holdout out of trained-on data is not possible — the
contamination already happened. This is the same discipline as the case-id split in our decision
model training, and the same reason we have not touched that test set.

```
"split": "train"     ← default
"split": "holdout"   ← sealed at creation, used only for evaluation
```

---

## Licensing — must be tracked, or "share" becomes a problem

The corpus draws on GitHub repositories (mostly MIT/Apache-2.0, but check each), blog posts
(copyright belongs to the author), Apple documentation (their terms), and arXiv papers (usually
permissive, but check). Training on and republishing are different acts with different
implications.

`SOURCES.md` records, for every source: URL, license if declared, and how we used it. If a source
is unlicensed or restrictive, we can still *read and cite it*, but not redistribute its text. We
keep claims (facts are not copyrightable) and drop verbatim prose.

---

## What we are deliberately not doing yet

- **No model training on this.** The corpus is small and young; training on it now would bake in
  errors we are still finding.
- **No automatic Q&A generation.** Deriving questions from claims is mechanical, and doing it
  before the claims are reviewed would multiply any error by the number of renderings.
- **No embedding index yet.** It becomes useful at a few thousand records, not a few hundred.

**The order is: claims, then review, then renderings.** Not the other way round.