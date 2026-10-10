# OpenClaims adoption — state

We adopted OpenClaims as the spine. This file records what has been converted, what was learned doing
it, and what the reference implementation teaches us.

## Converted and validated

`tools/to_openclaims.py` converts the whole knowledge base:

```
566 records            ->  claim.emitted   (554 knowledge-base + 12 origin events, P1 2026-10-03)
55 reviewer verdicts   ->  claim.verified   (verification_method: model_check)
53 Von verdicts        ->  claim.verified   (verification_method: model_check)
17 contested records   ->  claim.disputed
```

**Incremental extension (P2, 2026-10-10):** 50 records added since P1 (API/FORMAT/GOTCHAS/LANDSCAPE
and the EXP-026/027/028 findings) were appended by
[`tools/openclaims_append.py`](../tools/openclaims_append.py), bringing the spine to **616 `claim.emitted`
= 616 records**. The append path exists because `to_openclaims.py` regenerates wholesale and needs the
gitignored grounding cache to pin source digests / locate spans; on a cache-less clone a regeneration
would silently strip the pinned digests and spans the committed events already carry. The appender
builds the identical event shape via the same `complete()` helper, digests + validates each event with
the SDK, and preserves the existing lines byte-for-byte. New claims emitted without the cache carry no
`Source.digest` (as expected); the `claim.verified`/`claim.disputed` sets are unchanged.

All 108 `claim.verified` events are `model_check`; **zero are `human_review`**. The 55 reviewer
verdicts are an AI agent reading each claim against its cited passage — labelling them
`human_review` would be false provenance, which in a project whose purpose is provenance is worse
than a wrong number (an earlier revision of this converter did exactly that, and it was corrected).
`human_review` may appear only as a NEW, separately emitted verification written by a human-attested
pass; there is no code path in the converter that can produce it (`assert_no_human_review` enforces
this), and no such pass has happened yet.

**783 / 783 events validate with the Python SDK** (`to_openclaims.py --check`, re-run 2026-10-10;
658 `claim.emitted` + 108 `claim.verified` + 17 `claim.disputed`).
The earlier 679-event corpus also cross-validated against the project's own JavaScript
`validator-cli` (checked upstream at adoption time; that checkout is not on this machine, so the
12 origin events added by P1 are Python-validated only). Two validating independently is the point;
either one alone proves less.

Output: `openclaims/claims-{emitted,verified,disputed}.jsonl`

## What the conversion proved

**1. `support_type` is our verdict space.** No translation layer needed:
`yes -> supports_directly`, `partial -> supports_partially`, `no -> contradicts`.

**2. Two model validators sit side by side, and neither may sign a human's name.** The 55 reviewer
verdicts (agent reading the claim against its cited passage) and the 53 Von-1.0 NLI verdicts are
the same shape — `claim.verified`, `verification_method: model_check` — with different
`validator` provenance. They sit *beside* rather than replace each other, so a later check of
either kind appends history instead of overwriting it. A human review would be a third, distinct
`claim.verified` with `verification_method: human_review` and a human validator; the tool is unable
to write that label.

**3. Evidence became a pointer, and a miss is declared, not patched.** We recompute where each
passage sits inside its digest-pinned cached source and emit a real `text_span` (29 of the 55
reviewer verdicts carry one). The other 26 could not be located: those records carry **no evidence
at all** and the facet declares `evidence_status: unlocatable` — the earlier degenerate
`{start: 0, end: 0}` pointer was removed because it asserted evidence at the top of the file
regardless of content, and it still validated. A pointer that cannot be substantiated is removed
and the record says so.

**4. Our `confidence` label is retired into a facet.** It recorded how a claim was *established*
(measured/documented/inferred/claimed), not who *checked* it. And we measured that it carried no
signal about quality. The spine replaces it with `verification_result` + `verification_method` +
`validator`, which are answerable.

## Two bugs found in OpenClaims v0.1, both by validating

**1. Digest over a normalised payload.** `ClaimEvent` declares 20 fields. Emitting 11 produced a
digest that *verified against our own bytes* yet failed `validate_event`, because validation hashes
the model-normalised form. Fix: emit every declared field. The `schema_url` field — which the schema
requires and I had omitted — was caught the same way.

**2. Python and JavaScript compute different digests for `confidence: 1.0`.** Isolated by test:

| `confidence` | Python digest vs JS digest |
| --- | --- |
| 0.5 / 0.99 / 0.857 | **agree** |
| **1.0** | **disagree** — Python writes `1.0`, JS canonicalises to `1` |
| 1 (integer) | agree |

Emitting integer `1` fixes the JS side and breaks the Python side; the two are mutually incompatible
for this value. **The only form both accept is omitting the field when it is exactly 1.0**, which is
what the converter does. Worth reporting upstream.

## What the reference demo teaches

`examples/verified-analysis/` runs a versioned travel-policy corpus (`2026.3` → `2026.4`) and shows
the full lifecycle including a dispute raised by a *later document version*. Patterns we should adopt:

**Evidence carries `support_type` at emission.** The demo attaches evidence with a `page_span`
selector and `supports_directly` to the `claim.emitted` event itself, not only to the verification.
Our converter currently attaches evidence to the verified event instead — valid, but the demo's shape
is better: the evidence belongs to the claim from the moment it is asserted.

**`source_attestation` is a distinct method.** The demo uses it when the source itself is
authoritative, reserving `model_check` for when a model did the checking. For Apple's own
documentation this is the honest label — and it is stronger evidence than a model agreeing.

**A dispute names its evidence.** `claim.disputed` carries `dispute_rationale` *and*
`contradicting_evidence`. Our 17 contested records currently carry a rationale only; the
contradicting side should be attached.

**Sources are versioned.** `Source.version` distinguishes `2026.3` from `2026.4`. We have this
situation repeatedly — a finding that is later corrected — and the standard expresses it properly:
a new version disputes the old claim rather than editing it.

## Datasets

**OpenClaims ships no datasets.** It has conformance cases (4 valid, 5 invalid lifecycle fixtures),
4 valid + 5 invalid event fixtures, CloudEvents and JSON-LD exemplars, and one demo corpus. Nothing
usable as gold data for claim verification.

That is not a dead end: **because the spine is only a format, any public claim-verification dataset
can be converted into `claim.emitted` + `claim.verified` events.** That would give us far more gold
than the 55 items hand-labelled so far. A search for candidates is running separately.