# A lean agentic workflow for research sweeps — and why not Hermes

**The brief:** dedicated agents per venue, covering X / Reddit / GitHub / YouTube, digging for
anything relevant to local AI. Hermes was the usual tool, but it isn't lean any more and burns tokens.

---

## Why Hermes stopped being the right shape

Three things, and they compound:

1. **It carries a conversation.** Every venue's context accumulates in one thread, so by the fourth
   source you are paying to re-read the first three. Cost grows with the *square* of the sweep size.
2. **It reasons where it should just fetch.** A research sweep is mostly retrieval, filtering and
   citation — not deliberation. Paying a reasoning model to decide "is this URL worth opening" is the
   expensive way to do a cheap thing.
3. **No hard budget.** Nothing stops it, so it doesn't stop.

**The fix is structural, not a better prompt:** one agent per venue, each with no shared context and a
fixed output schema, and a single cheap pass that merges. Cost then grows *linearly* with venues.

---

## The shape

```
        ┌─ ScoutX      ─┐
        ├─ ScoutReddit ─┤
brief ──┼─ ScoutGitHub ─┼──►  findings (fixed schema, no prose)  ──►  merge + dedupe  ──►  report
        ├─ ScoutVideo  ─┤
        └─ ScoutPapers ─┘
```

**Five rules that carry the savings:**

| rule | why |
| --- | --- |
| **One venue per agent, no shared history** | context does not compound; cost is linear in venues |
| **Read-only scouts for retrieval** | the sweep is fetch-and-filter, not reasoning — use the cheap model |
| **Fixed output schema per finding** | merge and dedupe become mechanical, not another model call |
| **Every claim carries a URL** | a finding without a source is discarded, so hallucination is self-defeating |
| **A hard call budget per agent** | it stops on its own; no babysitting |

---

## The finding record

One schema, so a machine can merge them and a human can read them:

```
what        one sentence
url         required — no URL, no finding
venue       x | reddit | github | video | paper | news
matters     why it is relevant to us, one sentence
solidity    measured | claimed | opinion
date        YYYY-MM-DD if known
```

**`solidity` is the field that earns its place.** In this sweep it is what separated
`maderix/ANE`'s *"5–9% utilization"* (measured, and damning) from a vendor's *"193× faster"*
(claimed). Without it, those read the same.

---

## What this costs vs Hermes

For a five-venue sweep:

| | Hermes-style | this |
| --- | --- | --- |
| model calls | one growing thread | 5 fixed, parallel |
| context growth | quadratic | **flat** |
| stopping | open-ended | **budget-capped** |
| merging | more reasoning | **mechanical** |

The saving is not a smaller model — it is **not re-reading everything on every step.**

---

## What we already built for this, and can reuse

| piece | where |
| --- | --- |
| a fixed-schema extraction contract | the 18-agent JevBench extraction (`bench/verify_extraction.py`) |
| **deterministic verification of a model's output** | same file — rejects any value not in its source |
| parallel fan-out with per-slice output | the `task` batches used twice today |
| a generated report, never hand-typed | `bench/results_table.py --summary` |

**The extraction work today was this workflow, applied to our own reports.** The same shape serves a
web sweep; only the source changes.

---

## The one thing to add

**A merge step that dedupes by URL and sorts by `solidity`, then by relevance.** That is arithmetic,
not a model call — and it is the step Hermes spends its most expensive tokens on.

**And a rule worth keeping:** when a venue returns nothing relevant, the agent says so. A sweep that
reports five sources for five venues is suspicious; one that reports three plus two honest blanks is
informative.