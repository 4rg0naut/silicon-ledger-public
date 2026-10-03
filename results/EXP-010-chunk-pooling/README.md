# EXP-010 — testing EXP-009's own recommendation: chunk-and-pool does not pay

**Question.** EXP-009 closed by recommending *"chunk long documents to ~256–512 and max-pool"*.
That was an **assertion, not a measurement** — EXP-009 measured *truncation at a grid*, then
recommended chunking without testing it. This experiment tests the recommendation.

**Run:** 2026-09-20 · macOS 27.0 · base M4 · MTEB 2.21.0 · SciFact, `ndcg_at_10`

---

## Result — the recommendation is refuted

Whole-document embedding, three ways. `truncate` is the existing behaviour (body cut to S−2
tokens); `chunk+max`/`chunk+mean` split the body into S−2-token windows and pool the vectors.

| grid | **truncate** ndcg@10 | r@100 | **chunk+max** ndcg@10 | r@100 | **chunk+mean** ndcg@10 | r@100 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 128 | **0.65176** | 0.9283 | 0.56603 | 0.8877 | 0.64811 | **0.9350** |
| 256 | **0.67622** | **0.9417** | 0.64450 | 0.9193 | 0.65886 | 0.9333 |
| 512 | **0.68546** | 0.9450 | 0.67800 | 0.9383 | 0.66995 | 0.9450 |
| 1024 | **0.68760** | 0.9450 | — | — | — | — |

**Δ vs truncate, ndcg@10:** chunk+mean −0.004 / −0.017 / −0.016; chunk+max −0.086 / −0.032 / −0.007.

**Pooling into one vector never wins.** It is at best a tie on `recall@100` and a consistent loss
on `ndcg@10`.

## Why pooling loses

`ndcg@10` rewards ranking **the passage that answers the query** to the top. Pooling averages (or
maxes) the chunk vectors, so the document's single vector is a *blur of its parts* — it no longer
points at any one passage. The relevant evidence is still in the index (hence `recall@100` holds
up), but it can no longer be ranked first. That is exactly the signature in the table: recall
preserved, precision lost.

**Max-pool is the worse of the two**, and the reason is worth recording: element-wise max takes
each dimension's maximum *independently*, so the result is a "union of features" that corresponds
to no actual passage, and it sits off the distribution of the single-chunk vectors it is compared
against. At a 128 grid (3 windows per document) that costs **−0.086**; at 512 (usually 1–2 windows)
it is nearly harmless. The penalty scales with how much pooling actually happens.

## Why the corpus cannot show chunking's benefit

**SciFact passages are ~150–200 words (~200–400 tokens).** A 512 grid keeps 510 tokens — so
*truncation already sees essentially the whole document*, and chunking has nothing left to recover.
This experiment can refute "pooling helps here"; it **cannot** establish that chunking never helps.
That needs a genuinely long-document retrieval task, where a 512 grid discards most of the input.

## Revised recommendation

1. **Do not pool chunks into one vector.** Measured worse on ndcg@10 at every grid.
2. **If one vector per document is required, truncate at a large grid** (512) — it matches or beats
   every pooled variant.
3. **The real fix for long documents is to index each chunk separately**, so the query can match the
   best chunk directly instead of a blur of all of them. That is the standard two-stage shape and it
   is what `recall@100` ≈ 0.945 has been pointing at all along. This server's one-vector-per-input
   API cannot express it — it belongs in the memory system, not here.
   > **Measured in EXP-011: confirmed.** Chunk-indexed at S=128 scores `ndcg@10` **0.67923** /
   > `recall@100` **0.9550**, beating truncation at the same grid by +0.027/+0.027, beating both
   > pooling variants, and doing it with **less total ANE work** than truncating at 512 — for ~3×
   > the index vectors.
4. **Test on a long-document task** before concluding anything further.

## Caveats

- One task, one model, English. SciFact's short passages bound the conclusion (see above).
- The `--chunk`/`--pool` flags are **kept** even though pooling lost: they are the mechanism that
  produced this result, and they are what a long-document corpus would be tested with.
- Gates still only exist for the published 128/512 grids (EXP-009 caveat applies unchanged).

## Artifacts

- `tools/embed-server/embed_server.py` — `--chunk`, `--pool {max,mean}`; `/health` reports both
- `~/.cache/mteb/results/granite-chunk-s{128,256,512}/` — chunk+max
- `~/.cache/mteb/results/granite-chunkmean-s{128,256,512}/` — chunk+mean

---

## Measurements (generated)

> Generated from `results/measurements.json` by `bench/results_table.py`. **Do not hand-edit** — regenerate.
> Rows appear only when another row is genuinely comparable; `benchmark+split+scope+tiers+metric+unit`
> must agree. See `results/CONSISTENCY-PLAN.md` for why.

| id | model | placement | dtype | seq_len | metric | value | unit | latency_ms | latency_unit | provenance |
|---|---|---|---|---|---|---|---|---|---|---|
| granite-truncate-s128-ndcg10 | granite | — | — | 128 | ndcg@10 | 0.65176 | ndcg@10 | — | — | ours |
| granite-truncate-s256-ndcg10 | granite | — | — | 256 | ndcg@10 | 0.67622 | ndcg@10 | — | — | ours |
| granite-truncate-s512-ndcg10 | granite | — | — | 512 | ndcg@10 | 0.68546 | ndcg@10 | — | — | ours |
| granite-truncate-s1024-ndcg10 | granite | — | — | 1024 | ndcg@10 | 0.6876 | ndcg@10 | — | — | ours |
| granite-truncate-s128-recall100 | granite | — | — | 128 | recall@100 | 0.9283 | recall@100 | — | — | ours |
| granite-truncate-s256-recall100 | granite | — | — | 256 | recall@100 | 0.9417 | recall@100 | — | — | ours |
| granite-truncate-s512-recall100 | granite | — | — | 512 | recall@100 | 0.945 | recall@100 | — | — | ours |
| granite-truncate-s1024-recall100 | granite | — | — | 1024 | recall@100 | 0.945 | recall@100 | — | — | ours |
| granite-chunk-max-s128-ndcg10 | granite (chunk+max pool) | — | — | 128 | ndcg@10 | 0.56603 | ndcg@10 | — | — | ours |
| granite-chunk-max-s256-ndcg10 | granite (chunk+max pool) | — | — | 256 | ndcg@10 | 0.6445 | ndcg@10 | — | — | ours |
| granite-chunk-max-s512-ndcg10 | granite (chunk+max pool) | — | — | 512 | ndcg@10 | 0.678 | ndcg@10 | — | — | ours |
| granite-chunk-max-s128-recall100 | granite (chunk+max pool) | — | — | 128 | recall@100 | 0.8877 | recall@100 | — | — | ours |
| granite-chunk-max-s256-recall100 | granite (chunk+max pool) | — | — | 256 | recall@100 | 0.9193 | recall@100 | — | — | ours |
| granite-chunk-max-s512-recall100 | granite (chunk+max pool) | — | — | 512 | recall@100 | 0.9383 | recall@100 | — | — | ours |
| granite-chunk-mean-s128-ndcg10 | granite (chunk+mean pool) | — | — | 128 | ndcg@10 | 0.64811 | ndcg@10 | — | — | ours |
| granite-chunk-mean-s256-ndcg10 | granite (chunk+mean pool) | — | — | 256 | ndcg@10 | 0.65886 | ndcg@10 | — | — | ours |
| granite-chunk-mean-s512-ndcg10 | granite (chunk+mean pool) | — | — | 512 | ndcg@10 | 0.66995 | ndcg@10 | — | — | ours |
| granite-chunk-mean-s128-recall100 | granite (chunk+mean pool) | — | — | 128 | recall@100 | 0.935 | recall@100 | — | — | ours |
| granite-chunk-mean-s256-recall100 | granite (chunk+mean pool) | — | — | 256 | recall@100 | 0.9333 | recall@100 | — | — | ours |
| granite-chunk-mean-s512-recall100 | granite (chunk+mean pool) | — | — | 512 | recall@100 | 0.945 | recall@100 | — | — | ours |
| granite-chunk-mean-s128-delta-ndcg10 | granite (chunk+mean pool) | — | — | 128 | ndcg@10 delta vs truncate | 0.004 | absolute delta over truncate at grid 128 | — | — | ours |
| granite-chunk-mean-s256-delta-ndcg10 | granite (chunk+mean pool) | — | — | 256 | ndcg@10 delta vs truncate | 0.017 | absolute delta over truncate at grid 256 | — | — | ours |
| granite-chunk-mean-s512-delta-ndcg10 | granite (chunk+mean pool) | — | — | 512 | ndcg@10 delta vs truncate | 0.016 | absolute delta over truncate at grid 512 | — | — | ours |
| granite-chunk-max-s128-delta-ndcg10 | granite (chunk+max pool) | — | — | 128 | ndcg@10 delta vs truncate | 0.086 | absolute delta over truncate at grid 128 | — | — | ours |
| granite-chunk-max-s256-delta-ndcg10 | granite (chunk+max pool) | — | — | 256 | ndcg@10 delta vs truncate | 0.032 | absolute delta over truncate at grid 256 | — | — | ours |
| granite-chunk-max-s512-delta-ndcg10 | granite (chunk+max pool) | — | — | 512 | ndcg@10 delta vs truncate | 0.007 | absolute delta over truncate at grid 512 | — | — | ours |
