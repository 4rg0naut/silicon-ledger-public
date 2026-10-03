# The spine — OpenClaims

**Decision (user, this session): OpenClaims is the spine. Tools are now chosen by whether they can
speak to it, not by raw quality alone.** Finding a good tool and then inventing a format around it is
what we are replacing.

Repo: `github.com/openclaims-ai/openclaims` · v0.1 · schemas in `schemas/openclaims/0.1/`
Specifically: `Core.schema.json`, `BaseEvent.schema.json`, and the four event schemas.
TypeScript SDK, **Python SDK**, validator CLI, SQLite collector, JSON-LD export, conformance fixtures.

---

## Why it fits, and what it fixes

It is explicit that it is *not* a truth engine — it records provenance, support, verification and
lifecycle. Same stance as ours.

Three things it already had that we had been improvising:

**1. `inconclusive` is a first-class verification result.** Mid-labelling I invented a fourth category
(`insufficient`) for claims whose retrieved passage did not permit a judgement. The standard calls it
`inconclusive` and it is a required enum value.

**2. `verification_method` is mandatory.** `human_review | model_check | source_attestation |
consensus | formal_proof` — plus a typed `validator` (`Agent.agent_type: human | organization |
service | model | pipeline`). A model's verdict **cannot** be mistaken for a human's. This is exactly
the "same model marking its own homework" problem, solved structurally rather than by discipline.

**3. `support_type` is our verdict space.** `supports_directly` / `supports_partially` / `contradicts`
map one-to-one onto the `yes` / `partial` / `no` used in the 55 hand labels. Nothing to convert.

Plus: `Source.license` is a field (we wanted licence tracking), every event carries a `Digest`
(SHA-256, base64url), and events are **append-only**.

---

## The exact model

### Events (append-only)

`claim.emitted` → `claim.verified` → `claim.disputed` → `claim.retracted`

Every event requires: `event_id`, `event_type`, `event_time`, `spec_version`, `schema_url`,
`producer`, `claim` or `claim_ref`, `digest`.

A retraction **appends**; it never deletes the earlier belief. Our static records cannot express this,
and that matters for a corpus we intend to publish.

### Objects

| object | required fields | our use |
| --- | --- | --- |
| `Agent` | `agent_id`, `agent_type` (human/organization/service/**model**/pipeline) | who did a thing |
| `Claim` | `claim_id`, `text`, `claim_type`, `asserted_at` | one of our facts |
| `Source` | `source_id` (+ `uri`, `retrieved_at`, `digest`, **`license`**) | where it came from |
| `Evidence` | `evidence_id`, `source_ref`, **`selector`**, **`support_type`** | the exact text that bears on a claim |
| `Selector` | one of six shapes | **the pointer into the source** |
| `ToolRun` | `tool_run_id`, `tool_type`, `tool` ({name, version, model, model_version, …}) | reproducibility |
| `Verification` | `verification_id`, `verification_result`, `verification_method`, `claim_status`, `validator`, `verified_at` (+ optional `confidence` 0–1) | a check, by someone, at a time |
| `Inference` | `inference_id`, `method`, `input_refs`, `output_claim_ref` | derived claims |
| `Digest` | sha256 / base64url | tamper-evidence |
| `AuditableTrace` | `event_ids`, `hash_chain`, `signature_refs` | audit |

### Selectors — what "evidence" means now

```
text_span     {start, end}
page_span     {page, start, end}
json_pointer  {path}
table_cell    {row, column}
uri_fragment  {fragment}
byte_range    {start, end}
```

**This replaces our "evidence" blob.** We stored a slab of copied passage text. The spine stores a
*precise location*, so anyone can re-derive the evidence from the source and confirm it has not
drifted. That is a strictly better notion of what evidence is.

### The three verification dimensions (deliberately separate)

```
verification_result : supported | contradicted | inconclusive
verification_method : human_review | model_check | source_attestation | consensus | formal_proof
claim_status        : active | disputed | retracted
```

Three axes instead of our single `confidence` label. This dissolves a problem we hit: the helpers'
`confidence` labels carried **no signal** (`claimed` scored 100% solid, `measured` 70%). Under the
spine you never ask "how confident is this fact?" — you ask **who checked it, how, when, and what did
they find**, which is answerable and auditable.

### Claim-to-claim relations are first-class

```
relation_type: derived_from | summarizes | refines | contradicts
```

The contradiction layer needs no separate invention — a contradiction is a `ClaimRelation`, and a
`claim.disputed` event.

### Extensions

`Facet` requires `_producer` and `_schemaURL`, and allows anything else. This is where our
domain-specific fields live, namespaced:

| ours | becomes |
| --- | --- |
| `caveat` ("true on M3, not M1") | a facet on `Claim` or `Evidence` |
| `kind` (gotcha / procedure / measurement / …) | a facet — `claim_type` is coarser and does not carry this |
| `topic`, `entities` | facets, for retrieval keys |

---

## The tool contract — what every layer must emit

This is the part that changes how we choose tools.

| layer | must produce | spine object | a tool without this |
| --- | --- | --- | --- |
| **parse** | text + page/table positions | `Source`, `Selector: page_span/table_cell` | cannot anchor evidence → weak |
| **extract** | candidate claims + **exact spans** | `Evidence`, `Selector: text_span` | prose output is unusable |
| **label** | `claim_type` + `kind` facet | `Claim`, `Facet` | acceptable; labels are fields |
| **verify** | verdict + **who** + confidence | `Verification`, `Evidence.support_type` | must at minimum declare `verification_method` |
| **reconcile** | claim-to-claim relation | `ClaimRelation` | prose output is unusable |
| **retrieve** | ranked source refs | `Source` | acceptable |
| **all** | tool name + version + params | `ToolRun` | not reproducible → weaker evidence |

Every tool call gets wrapped in a `ToolRun`. Nothing is updated in place; a new verdict is a new
`claim.verified` event.

---

## How this re-ranks the candidates we tested

**Verify.** We scored Von 70% and LettuceDetect 62% on verdict accuracy. Under the spine:

- **Von** emits a verdict and a probability — but **no selector** ✗
- **LettuceDetect emits character spans** — which *are* `Evidence.selector` ✓✓✓

So LettuceDetect is more valuable than its accuracy score suggests, because it produces the evidence
pointer the spine requires. **The right answer is probably both**: LettuceDetect for the *selector*,
Von for the *verdict*, recorded as two `claim.verified` events with `verification_method: model_check`
and distinct validators. The spine makes composition natural instead of needing a combined model.

**Extract.** GLiNER2.5 returns char spans with confidence → directly `Evidence` + `text_span` +
`confidence`. GLiNER-Relex returns `(head, relation, tail)` with offsets → spans plus
`ClaimRelation`. **Both are spine-native**, which is a point in their favour that our earlier
accuracy-only test could not have seen.

**Parse.** The spine explains why layout-aware parsers (MinerU, docling.rs) matter: they are the only
ones that can give you `page_span` and `table_cell` anchors for a PDF. A parser that returns flat text
cannot anchor anything.

**Gaps — no tool exists, we must build the glue:**

1. **Nothing produces `ToolRun` metadata.** Every model invocation needs wrapping.
2. **Nothing maps a URL source to text offsets** for `text_span` selectors. Our cached sources are
   raw text; offsets must be relative to a digest-pinned copy, or they are meaningless later.
3. **Nothing maps our `kind` to facets.**
4. **The `inconclusive` case must be produced deliberately** — a tool that only answers yes/no cannot
   express it.

---

## What our existing work becomes

| today | under the spine |
| --- | --- |
| 554 records in `records/*.jsonl` | 554 `claim.emitted` events + `Source` + `Evidence` |
| 118 sources with licence notes | `Source` objects with `license`, `retrieved_at`, `digest` |
| the 55 hand labels | 55 `claim.verified` events, `verification_method: human_review` |
| Von's 53 verdicts | `claim.verified`, `verification_method: model_check`, validator agent_type `model` |
| the 2 `insufficient` items | `verification_result: inconclusive` |
| `contested: true` on 17 records | `ClaimRelation.contradicts` + `claim.disputed` |
| our `confidence` label | **retired** — replaced by Verification + Evidence |

**The hand labels stop being a one-off test set** and become the opening entries of a permanent
verification history that a model's verdicts sit *beside* rather than replace.

---

## Order of work

1. **Convert** the 554 records and 55 labels into events; validate with their CLI. Proves the spine
   holds our data.
2. **Build the adapter** — one wrapper that turns any tool output into `Evidence` + `Verification` +
   `ToolRun`. Every later tool plugs into this and nothing else.
3. **Re-run the layer evaluations emitting spine objects**, not just accuracy numbers, and re-rank on
   both axes.
4. Only then choose the final stack.