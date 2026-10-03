# EXP-014 — where we actually stand, and what was actually achieved

**Question.** Our reranked pipeline scored 0.75860 on SciFact, above published bge-base (0.74345).
Is that a real result, or a comparison error?

**Answer: it was a comparison error.** EXP-012 set our *reranked* pipeline against bge-base
*unreranked*. A reranked pipeline beating an unreranked model is not a finding.

**Run:** 2026-09-21 · SciFact · 300 queries · K=20 shortlist · same ANE reranker for both arms

---

## The fair comparison: same reranker, different retriever

| retriever | params | base ndcg@10 | + reranker | delta | base recall@10 |
| --- | ---: | ---: | ---: | ---: | ---: |
| **ours** (Granite-97M, chunk-indexed, ANE) | 97M | 0.67923 | **0.75860** | **+0.07937** | 0.80233 |
| **bge-base-en-v1.5** (one vector/doc) | 109M | 0.73763 | **0.77204** | +0.03441 | 0.86589 |

**bge-base + our reranker beats ours + our reranker by +0.013.** And its retriever alone beats our
retriever by **+0.058**.

## So what did we actually achieve?

**Not a state-of-the-art retrieval score.** Stated plainly:

| | ndcg@10 |
| --- | ---: |
| our retriever alone | 0.67923 |
| bge-base alone | 0.73763 |
| our full pipeline | 0.75860 |
| **bge-base + the same reranker** | **0.77204** |

Our 97M retriever performs below a 109M one trained for the job, and a reranker does not close it.
**Our retriever is the weak half of the stack.**

**What is genuinely ours:**

1. **The whole pipeline runs on the Neural Engine** — embedder *and* reranker. The bge-base arm
   above ran on CPU. That is the actual differentiator, and it is a real one: nothing in the zoo
   had a cross-encoder on the ANE, and the published bundle compiled to **0 ANE regions**.
2. **The reranker contributes more to a weaker shortlist** (+0.0794 vs +0.0344). It is doing real
   work, not riding on the retriever.
3. **The ANE re-authoring knowledge** — five concrete changes, one of which (RoPE as input) was
   the difference between a segfaulting compiler and full ANE residency.

**What is not ours:** the models. Both are published checkpoints; we re-shaped and ported them.

## The honest framing

> We did not build a better retriever. We built a **fully on-device pipeline** that is competitive
> but behind a well-trained 109M baseline, and we learned how to put a cross-encoder on the
> Neural Engine — which was previously undocumented and, for this bundle, impossible.

The interesting engineering here is the **port**, not the score. Anyone reading only the headline
ndcg would draw the wrong conclusion about what this work is.

## Caveats

- One task (SciFact), one language, one grid (S=512), one chip (M4/h16g).
- ~~Our retriever is chunk-indexed at S=128 while bge-base is one vector per document — a
  difference in *method*, so the +0.058 gap is not purely model quality.~~
  **Resolved, and it does not help us.** EXP-009 already measured our retriever in bge-base's own
  mode (one vector per document):

  | our retriever | ndcg@10 |
  | --- | ---: |
  | chunk-indexed S=128 (EXP-011) | 0.65176 |
  | whole-doc truncate S=512 (EXP-009) | 0.68546 |
  | **whole-doc truncate S=1024** (best) | **0.68760** |
  | bge-base-en-v1.5, same mode | 0.73763 |

  So even in the same method our best configuration is **0.050 behind**. The gap is model quality,
  not method — the caveat above was too generous to us.
- bge-base ran on CPU here, so the comparison says nothing about energy or throughput — where the
  ANE stack's case is strongest.
- `recall@10` before reranking is 0.802 (ours) vs 0.866 (bge-base): our shortlist is the weaker
  input, which is exactly why the reranker gains more on it.

## Artifacts

- `bench/compare_retrievers.py` — the harness (same reranker, swappable retriever)
- `work/mteb/retriever_bge-base-en-v1.5_k20.json`, `work/mteb/rerank_k20_ane.json`

---

## Measurements (generated)

> Generated from `results/measurements.json` by `bench/results_table.py`. **Do not hand-edit** — regenerate.
> Rows appear only when another row is genuinely comparable; `benchmark+split+scope+tiers+metric+unit`
> must agree. See `results/CONSISTENCY-PLAN.md` for why.

| id | model | placement | dtype | seq_len | metric | value | unit | latency_ms | latency_unit | provenance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| granite97m-chunk-ane-base | Granite-97M | ANE | — | 512 | ndcg@10 (base retriever) | 0.67923 | ndcg@10 | — | — | ours |
| granite97m-chunk-ane-reranked | Granite-97M | ANE | — | 512 | ndcg@10 (with reranker) | 0.7586 | ndcg@10 | — | — | ours |
| granite97m-chunk-ane-delta | Granite-97M | ANE | — | 512 | ndcg@10 delta | 0.07937 | absolute delta over base ndcg@10 | — | — | ours |
| granite97m-chunk-ane-recall10 | Granite-97M | ANE | — | 512 | recall@10 | 0.80233 | recall@10 | — | — | ours |
| bgebase-cpu-base | bge-base-en-v1.5 | CPU | — | 512 | ndcg@10 (base retriever) | 0.73763 | ndcg@10 | — | — | ours |
| bgebase-cpu-reranked | bge-base-en-v1.5 | CPU (retriever), ANE (reranker) | — | 512 | ndcg@10 (with reranker) | 0.77204 | ndcg@10 | — | — | ours |
| bgebase-cpu-delta | bge-base-en-v1.5 | CPU (retriever), ANE (reranker) | — | 512 | ndcg@10 delta | 0.03441 | absolute delta over base ndcg@10 | — | — | ours |
| bgebase-cpu-recall10 | bge-base-en-v1.5 | CPU | — | 512 | recall@10 | 0.86589 | recall@10 | — | — | ours |
