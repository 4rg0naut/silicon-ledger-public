# EXP-012 — the cross-encoder reranker closes the ranking gap

**Question.** EXP-011 left the pipeline at `recall@100 = 0.9550` but `ndcg@10 = 0.67923`: the
candidates are retrieved, they are just not *ordered*. The oracle headroom was **+0.2758**. How
much of it does a real reranker capture?

**Run:** 2026-09-20 · macOS 27.0 · base M4 · SciFact, 5,183 docs / 300 queries · shortlist K=20

---

## Result — +0.0786 ndcg@10, and the pipeline passes bge-base

The same shortlist is scored twice — once in the retriever's order, once in the reranker's — so the
only thing that changes is the ordering within it.

| | ndcg@10 | recall@10 |
| --- | ---: | ---: |
| retriever order (baseline) | 0.67923 | 0.80233 |
| **+ Qwen3-Reranker-0.6B** | **0.75784** | **0.85900** |
| | **+0.07861** | +0.05667 |
| ceiling (relevant doc is in the shortlist) | 0.8740 | — |

**The baseline reproduces EXP-011's full-corpus `ndcg@10` exactly (0.67923)** — the top-10 comes
entirely from the top-20, so the shortlist restriction costs nothing and the two harnesses agree.

> **CORRECTION (EXP-014).** The table below compares our *reranked* pipeline against bge-base
> *unreranked*. **That is not a fair comparison and the claim it implies does not hold.** Running
> the same reranker over a bge-base shortlist gives **0.77204**, so bge-base + reranker beats us by
> +0.013. See EXP-014. The reranker's *own* contribution (+0.0794 here) is real; the "beats
> bge-base" framing is not.

| | ndcg@10 |
| --- | ---: |
| our embedder alone | 0.67923 |
| **our embedder + reranker** | **0.75784** |
| published bge-base (109M) | 0.74345 |
| published bge-small (33M) | 0.71273 |
| published all-MiniLM-L6 (22M) | 0.64508 |

**The pipeline now beats bge-base** — a 97M ANE embedder plus a 0.6B GPU reranker on a shortlist of
20, against a 109M single-model baseline.

## Cost

- **3.40 s/query** at K=20 (20 pair-scores), i.e. **~170 ms per pair** on the base M4 GPU.
- Full run: **1,021 s** for 300 queries.
- The zoo measured 45.7 ms/pair on an M4 **Max** GPU; 170 ms on a base M4 is ~3.7× that, consistent
  with the GPU difference.
- **The reranker is a shortlist cost, not a corpus cost** — it runs 20 pairs per query, not 5,183.
  That is what makes a 0.6B cross-encoder affordable locally at all.

## Where the remaining headroom is

At K=20 the ceiling is **0.8740** and reranked `recall@10` is **0.8590** — so the reranker nearly
saturates its shortlist (in a 20-query pilot it saturated it *exactly*: `recall@10` 0.9000 against a
0.9000 ceiling). **The binding constraint is now the shortlist size, not the reranker.** EXP-011's
`recall@100 = 0.9550` says a K=100 shortlist would raise the ceiling to 0.9550, at ~5× the rerank
cost (≈81 min for 300 queries). That is the obvious next lever, and it is a compute knob rather than
a modelling problem.

## Two bugs found, one of them silent and severe

**1. The ANE delegate returns a constant `[0.5, 0.5]` for this bundle.** No error, no warning — a
plausible-looking "uncertain" score that would have made the reranker a silent no-op or a random
tie-breaker, and the pipeline would still have "improved" sometimes.

| delegate | `probs` for a relevant pair |
| --- | --- |
| ANE | `[0.5, 0.5]` ❌ |
| GPU | `[0.00619, 0.9937]` ✅ |
| CPU | `[0.006306, 0.994]` ✅ |
| official | `0.993775` |

The zoo's own gate is GPU-delegate and its latency numbers are "M4 Max GPU", so the ANE path was
never validated for this bundle. GPU also loads in ~0.9 s against the ANE's ~17 s. **The server runs
on the GPU deliberately, and the gate is checked before any measurement.**

**2. My own server never actually adopted its inherited socket.** On recycle it printed *"adopted
inherited listening socket"* while constructing a *new* `ThreadingHTTPServer` — which fails with
`Errno 48` because the inherited fd still holds the port. It killed the first full run at query 180.
The fix is `socket.fromfd` + `bind_and_activate=False` (the pattern the embed server already used).
Verified with `--restart-every 12`: 30 requests, 2 recycles, **0 failures** — then confirmed in
production, where the run crossed the same boundary with `recycles: 1, adoptions: 1` and finished.

Both are the same lesson as EXP-009/010: **a silent wrong answer is worse than a loud failure, and
"it ran" is not "it measured".**

## Caveats

- **The reranker was not gated on SciFact**, only on the zoo's 6-pair reference set (which it passes:
  worst |Δ| 2.23e-04, all rank groups correct, separation +0.9814). A reranker that is subtly wrong
  on this corpus would still show a lift.
- One task, one model, English. The mechanism transfers; the numbers need not.
- K=20 only. Larger shortlists were not measured (see above).
- 170 ms/pair is base-M4 GPU. On an M4 Pro/Max this would be substantially faster.

## Artifacts

- `tools/rerank-server/rerank_server.py` — the server (GPU delegate, socket adoption, recycle)
- `tools/rerank-server/gate_reranker.py` — the reference gate (passes)
- `bench/rerank_retrieval.py` — the harness (caches the chunk index; isolates the reranker)
- `models/qwen3-reranker/` — the bundle + tokenizer + reference.json
- `work/mteb/rerank_k20_full.json` — the raw result

---

## Measurements (generated)

> Generated from `results/measurements.json` by `bench/results_table.py`. **Do not hand-edit** — regenerate.
> Rows appear only when another row is genuinely comparable; `benchmark+split+scope+tiers+metric+unit`
> must agree. See `results/CONSISTENCY-PLAN.md` for why.

| id | model | placement | dtype | seq_len | metric | value | unit | latency_ms | latency_unit | provenance |
|---|---|---|---|---|---|---|---|---|---|---|
| retriever-order-baseline-ndcg10 | our embedder | ANE | — | — | ndcg@10 | 0.6792 | ndcg@10 | — | — | ours |
| retriever-order-baseline-recall10 | our embedder | ANE | — | — | recall@10 | 0.8023 | recall@10 | — | — | ours |
| qwen3-reranker-k20-ndcg10 | Qwen3-Reranker-0.6B | GPU | — | — | ndcg@10 | 0.7578 | ndcg@10 | — | — | ours |
| qwen3-reranker-k20-recall10 | Qwen3-Reranker-0.6B | GPU | — | — | recall@10 | 0.859 | recall@10 | — | — | ours |
| reranker-delta-ndcg10 | Qwen3-Reranker-0.6B | GPU | — | — | ndcg@10 | 0.07861 | absolute delta over retriever order (baseline), ndcg@10 | — | — | ours |
| reranker-delta-recall10 | Qwen3-Reranker-0.6B | GPU | — | — | recall@10 | 0.05667 | absolute delta over retriever order (baseline), recall@10 | — | — | ours |
| k20-ceiling-ndcg10 | shortlist K=20 ceiling (relevant doc is in the shortlist) | — | — | — | ndcg@10 | 0.874 | ndcg@10 | — | — | ours |
| pilot-reranked-recall10 | Qwen3-Reranker-0.6B | GPU | — | — | recall@10 | 0.9 | recall@10 | — | — | ours |
| pilot-ceiling-recall10 | shortlist K=20 ceiling (relevant doc is in the shortlist) | — | — | — | recall@10 | 0.9 | recall@10 | — | — | ours |
| rerank-latency-per-query-k20 | Qwen3-Reranker-0.6B | GPU | — | — | latency per query | 3.4 | s | 3400 | per query at K=20 (20 pair-scores) (report states 3.4 s; stored as ms) | ours |
| rerank-latency-per-pair | Qwen3-Reranker-0.6B | GPU | — | — | latency per pair | 170 | ms | 170 | per pair (cross-encoder pair score) | ours |
| rerank-full-run-seconds | Qwen3-Reranker-0.6B | GPU | — | — | full run wall time | 1021 | s | 1021000 | per full run (300 queries) (report states 1021 s; stored as ms) | ours |
| zoo-latency-per-pair-m4-max | Qwen3-Reranker-0.6B | GPU | — | — | latency per pair | 45.7 | ms | 45.7 | per pair (cross-encoder pair score) | ours |
| correction-our-embedder-alone-ndcg10 | our embedder | ANE | — | — | ndcg@10 | 0.6792 | ndcg@10 | — | — | ours |
| correction-our-embedder-plus-reranker-ndcg10 | our embedder + Qwen3-Reranker-0.6B | GPU | — | — | ndcg@10 | 0.7578 | ndcg@10 | — | — | ours |
| scifact-gpu-exp012-ndcg10 | Qwen3-Reranker-0.6B | GPU | — | 512 | ndcg@10 | 0.7578 | ndcg@10 | — | — | ours |
| scifact-gpu-exp012-recall10 | Qwen3-Reranker-0.6B | GPU | — | 512 | recall@10 | 0.859 | recall@10 | — | — | ours |
| scifact-gpu-exp012-total-time | Qwen3-Reranker-0.6B | GPU | — | 512 | pipeline wall-clock time (300 queries) | 1021 | s | — | — | ours |
| scifact-gpu-exp012-per-query | Qwen3-Reranker-0.6B | GPU | — | 512 | pipeline wall-clock per query | 3.4 | s/query | — | — | ours |
| gate-worst-abs-deviation | Qwen3-Reranker-0.6B | GPU | — | — | worst |delta| vs reference | 0.000223 | absolute probability delta | — | — | ours |
| gate-separation | Qwen3-Reranker-0.6B | GPU | — | — | separation | 0.9814 | separation | — | — | ours |
| delegate-ane-relevant-pair-score | Qwen3-Reranker-0.6B | ANE | — | — | relevant-pair score (positive class; probs [0.5, 0.5]) | 0.5 | probability | — | — | ours |
| delegate-gpu-relevant-pair-score | Qwen3-Reranker-0.6B | GPU | — | — | relevant-pair score (positive class; probs [0.00619, 0.9937]) | 0.9937 | probability | — | — | ours |
| delegate-cpu-relevant-pair-score | Qwen3-Reranker-0.6B | CPU | — | — | relevant-pair score (positive class; probs [0.006306, 0.994]) | 0.994 | probability | — | — | ours |
| official-relevant-pair-score | Qwen3-Reranker-0.6B (official reference) | — | — | — | relevant-pair score (official reference) | 0.9938 | probability | — | — | ours |
| gpu-delegate-load-time | Qwen3-Reranker-0.6B | GPU | — | — | delegate load time | 0.9 | s | 900 | per server/delegate load (startup) | ours |
| ane-delegate-load-time | Qwen3-Reranker-0.6B | ANE | — | — | delegate load time | 17 | s | 17000 | per server/delegate load (startup) (report states 17 s; stored as ms) | ours |
