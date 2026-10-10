# Cross-repo contract — silicon-ledger and silicon-ledger-bench

Both repositories ship v0.1 against this contract. It exists because every item below is a
**join key**: a value that two independently-produced corpora are merged on. A divergence here does
not cause an error — it causes silence, which is worse.

## Join keys

| key | value | note |
| --- | --- | --- |
| schema id | **`silicon-ledger/1`** | project-wide, NOT per-repo. A per-repo id forks every cross-machine diff. |
| `_producer` | the **bare repository name** — `silicon-ledger`, `silicon-ledger-bench` | not a URN. Same *form* on both sides, so a reader sees which instrument wrote a record without resolving anything. |
| facet key | the producer's name, e.g. `facets: {"silicon-ledger": {…}}` | one facet per producer; the two field sets are deliberately disjoint so a merged ledger is filterable by facet key alone. |
| facet schema | `schemas/facets/<producer>/1.json` **in the producer's own repo** | referenced by raw URL. Each producer's schema resolves inside its own tree, so neither can dangle the other's identifiers. No Pages dependency. |

## Verification vocabulary

**Machines may stamp `model_check` only.** `verification_method: "human_review"` appears solely as a
new, separately emitted `claim.verified` event written by a human-attested pass. There is no code
path in either tool that can produce it — an earlier revision of the ledger converter labelled 55
agent-produced verdicts `human_review`, and in a project whose purpose is provenance a false label is
worse than a wrong number.

## Evidence honesty

**Unverifiable evidence is declared, never asserted.** A pointer that cannot be substantiated is
removed and the record says so — a degenerate pointer that still validates is the worst outcome,
because nothing downstream can detect it.

`evidence_status`: `ok` · `unlocatable` · `stale`, checked in that order:

1. **digest** — does the source still hash to the digest pinned at emission? If not → `stale`
2. **location** — does the cited passage still occur in it? If not → `unlocatable`

The two are sequential and mutually exclusive, which is why this is one field rather than two
booleans. Both are non-LLM, at write time.

## Launch state, stated honestly

Every claim in both corpora at v0.1 is **model-checked**. No human has verified any of them. Where
evidence could not be substantiated, none is claimed and the record says so.

## Schema URL reachability, stated honestly

The facet key `_schemaURL` pins each producer's facet schema to a `raw.githubusercontent.com` URL.
That resolution depends on the repository being **public**:

- **`silicon-ledger-bench`** — public; its facet schema lands with the v0.1.x facet work and its
  URL then resolves.
- **`silicon-ledger`** — **private, stays private** (owner decision); logged out it returns
  **HTTP 404**, which is correct. The published content lives in its public mirror
  **`silicon-ledger-public`**, and this contract hereby declares the **mirror the canonical
  public host** for the schema URL:
  `https://raw.githubusercontent.com/4rg0naut/silicon-ledger-public/main/schemas/facets/silicon-ledger/1.json`
  — it resolves (HTTP 200). The mirror is regenerated deterministically by
  `tools/publish/publish.sh` (redaction rules in `tools/publish/redaction.json`) and pushed by
  `tools/publish/push-mirror.sh`, squashed per publication, each mirror commit carrying a
  `source-commit:` trailer naming the private commit it was generated from.

Consumers validating facets over the network must pin the mirror URL above; the private-repo
URL of the same path remains 404 by design. Publication log, 2026-10-03: mirror initialised at
`36c44bb` from private `0d7f1f1` (259 files) — mirror schema URL → **200**, private repo
logged out → **404**, both verified with `curl` at publication time.
