# EXP-011 — indexing chunks separately: the fix EXP-010 inferred, now measured

**Question.** EXP-010 showed pooling chunks into one vector loses to plain truncation, and
concluded that the real fix for long documents is to **index each chunk separately** so a query can
match the best chunk directly rather than a blur of all of them. That was an inference from a
negative result, not a measurement. This measures it.

**Run:** 2026-09-20 · macOS 27.0 · base M4 · SciFact, grid S=128, 5,183 docs / 300 queries

---

## Result — confirmed, and it is the best result measured so far

Every document is split into 126-token chunks (S−2), each chunk embedded separately, and a
document's score for a query is the **max cosine over its chunks**.

| method | grid | ndcg@10 | recall@100 |
| --- | ---: | ---: | ---: |
| truncate | 128 | 0.65176 | 0.9283 |
| chunk+max-pool | 128 | 0.56603 | 0.8877 |
| chunk+mean-pool | 128 | 0.64811 | 0.9350 |
| **chunk-indexed (separate)** | **128** | **0.67923** | **0.9550** |
| truncate | 512 | 0.68546 | 0.9450 |
| truncate | 1024 | 0.68760 | 0.9450 |

**Δ vs the same grid truncated:** +0.0275 ndcg@10, **+0.0267 recall@100**.
**Δ vs pooling at the same grid:** +0.031 ndcg@10 over mean-pool, +0.113 over max-pool.

**`recall@100 = 0.9550` is the highest of anything measured in this project** — higher than
truncating at 512 or 1024.

## The cost comparison favours it too

| | embeddings | grid | ANE work (token-positions) | index vectors |
| --- | ---: | ---: | ---: | ---: |
| truncate @512 | 5,183 | 512 | 2.65 M | 5,183 |
| truncate @1024 | 5,183 | 1024 | 5.31 M | 5,183 |
| **chunk-indexed @128** | 15,508 | 128 | **1.99 M** | 15,508 |

Chunk-indexing at a 128 grid does **25% less total ANE work than truncating at 512** and **63% less
than at 1024**, while achieving **higher recall@100**. The price is index size — **2.99× the
vectors** (15,508 for 5,183 docs; mean 2.99 chunks/doc, max 15).

So the honest trade is: **~3× index storage buys better recall at less compute.** For a local
memory system that is a good trade; storage is cheap and the ANE is the scarce resource.

## Cross-harness verification (added 2026-09-21)

This experiment's headline compares a **hand-rolled** number (chunk-indexed 0.67923, from
`bench/chunk_indexed_retrieval.py`) against an **MTEB** number (truncate 0.65176, from
`bench/mteb_retrieval.py`). Comparing across two harnesses is exactly the kind of error that
invalidated EXP-012's first conclusion, so it was checked directly: the *same* hand-rolled harness
run with `--mode truncate` (one vector per document — what MTEB measures) gives

| harness | mode | ndcg@10 | recall@100 |
| --- | --- | ---: | ---: |
| MTEB | truncate S=128 | 0.65176 | 0.9283 |
| hand-rolled | truncate S=128 | **0.65255** | **0.9283** |

**`recall@100` identical to four decimals, `ndcg@10` within 0.0008.** The harnesses agree, so the
+0.0267 gain from chunk-indexing is real and not a measurement artifact.

Note this also means the *MTEB* number for chunk-indexing would be the one to quote alongside other
MTEB results; the hand-rolled figure is used here because MTEB scores one vector per corpus entry
and so cannot express chunk-level indexing at all.

## Why this works where pooling did not

The document's evidence is now *addressable*. Under pooling, a 3-chunk document became one blurred
vector — the relevant passage was in the index but could not be ranked first (`recall@100` held,
`ndcg@10` fell). With separate chunks, the query's own vector is compared against each chunk
individually, so the chunk that actually answers it can win outright. That is exactly the
signature observed: pooling preserved recall and lost precision; chunk-indexing improves **both**.

## What this means for the pipeline

`recall@100 = 0.9550` means the candidate set is now very nearly complete — the two-stage shape is
in place. The remaining gap is `ndcg@10 = 0.679`, i.e. *ranking within* the candidate set. That is
a reranker's job, and this experiment strengthens the case: there is almost nothing left to find,
and plenty left to order correctly.

## Caveats

- **SciFact passages are ~200–400 tokens**, so at a 512 grid chunk-indexing would collapse to
  ~1 chunk/doc and show no gain. The benefit here is specific to **small grids on documents longer
  than the grid**. A genuinely long-document task would show it more strongly.
- The score is `max` over chunks; alternatives (e.g. summing the top-k chunks, or weighting by
  chunk position) were not tried.
- One task, one model, English. The mechanism should transfer; the absolute numbers need not.
- The harness scores by hand rather than through MTEB (MTEB scores one vector per corpus entry, so
  it cannot express chunk-level indexing). The metric definitions match MTEB's: `ndcg@10` with
  binary relevance, `recall@100` over the top 100.

## Artifacts

- `bench/chunk_indexed_retrieval.py` — the harness (loads SciFact, builds the chunk index, scores)
- `tools/embed-server/embed_server.py` — `POST /v1/chunk_embeddings` returns unpooled chunk vectors
- `work/mteb/chunkindexed_s128.json` — the raw result


---

## Measurements (generated)

> Generated from `results/measurements.json` by `bench/results_table.py`. **Do not hand-edit** — regenerate.
> Rows appear only when another row is genuinely comparable; `benchmark+split+scope+tiers+metric+unit`
> must agree. See `results/CONSISTENCY-PLAN.md` for why.

| id | model | placement | dtype | seq_len | metric | value | unit | latency_ms | latency_unit | provenance |
|---|---|---|---|---|---|---|---|---|---|---|
| exp011-chunk-indexed-s128-ndcg10 | granite (chunk-indexed, one vector per chunk) | — | — | 128 | ndcg@10 | 0.67923 | ndcg@10 | — | — | ours |
| exp011-chunk-indexed-s128-recall100 | granite (chunk-indexed, one vector per chunk) | — | — | 128 | recall@100 | 0.955 | recall@100 | — | — | ours |
| exp011-chunk-indexed-s128-delta-ndcg10 | granite (chunk-indexed, one vector per chunk) | — | — | 128 | ndcg@10 delta vs truncate | 0.027 | absolute delta over truncate at grid 128 | — | — | ours |
| exp011-chunk-indexed-s128-delta-recall100 | granite (chunk-indexed, one vector per chunk) | — | — | 128 | recall@100 delta vs truncate | 0.027 | absolute delta over truncate at grid 128 | — | — | ours |
| chunk-indexed-separate-s128-ndcg10 | — | ANE | — | 128 | ndcg@10 | 0.67923 | ndcg@10 | — | — | ours |
| chunk-indexed-separate-s128-recall100 | — | ANE | — | 128 | recall@100 | 0.955 | recall@100 | — | — | ours |
| cost-chunk-indexed-s128-embeddings | — | ANE | — | 128 | embeddings | 15508 | embeddings | — | — | ours |
| cost-chunk-indexed-s128-ane-work | — | ANE | — | 128 | ANE work | 1.99 | M token-positions | — | — | ours |
| cost-chunk-indexed-s128-index-vectors | — | ANE | — | 128 | index vectors | 15508 | index vectors | — | — | ours |
| hand-rolled-harness-truncate-s128-ndcg10 | — | ANE | — | 128 | ndcg@10 | 0.65255 | ndcg@10 | — | — | ours |
| hand-rolled-harness-truncate-s128-recall100 | — | ANE | — | 128 | recall@100 | 0.9283 | recall@100 | — | — | ours |
| delta-chunk-indexed-vs-truncate-s128-ndcg10 | — | ANE | — | 128 | ndcg@10 | 0.0275 | absolute delta over truncate S=128 | — | — | ours |
| delta-chunk-indexed-vs-truncate-s128-recall100 | — | ANE | — | 128 | recall@100 | 0.0267 | absolute delta over truncate S=128 | — | — | ours |
| delta-chunk-indexed-vs-mean-pool-s128-ndcg10 | — | ANE | — | 128 | ndcg@10 | 0.031 | absolute delta over chunk+mean-pool S=128 | — | — | ours |
| delta-chunk-indexed-vs-max-pool-s128-ndcg10 | — | ANE | — | 128 | ndcg@10 | 0.113 | absolute delta over chunk+max-pool S=128 | — | — | ours |
| granite-chunk-indexed-s128-exp011 | Granite-97M | ANE | — | 128 | ndcg@10 | 0.65176 | ndcg@10 | — | — | ours |
