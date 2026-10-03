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
- **`silicon-ledger`** — **private until publication** (owner decision). Its URL
  (`.../silicon-ledger/main/schemas/facets/silicon-ledger/1.json`) therefore returns **HTTP 404**
  today. This is **declared, not asserted**: the schema file is committed in-repo at
  `schemas/facets/silicon-ledger/1.json` and the URL becomes live at publication; no facet data
  depends on URL reachability for local consumption (the schema travels with the corpus), and the
  URL is a forward-pinned identifier, not evidence.

Until the ledger repo is public, a consumer validating facets over the network will find a
dangling identifier on the `silicon-ledger` side. That is the honest state; it changes in one
action (publishing the repo), after which both URLs resolve and no record needs to change.
