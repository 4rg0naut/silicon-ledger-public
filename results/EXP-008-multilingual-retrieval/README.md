# EXP-008 — multilingual retrieval: is the embedder good enough *in French*?

**Question.** EXP-007 measured the ANE embedder on **English** only, where it was competent but
not class-leading. But the actual use case is **multilingual** — French documents first, and
eventually any language. Before porting a different model, measure the one we have.

**Run:** 2026-09-20 · macOS 27.0 · base M4 · MTEB 2.21.0 · `MultilingualNanoSciFactRetrieval`

---

## Result — the model is multilingual, and it beats the standard reference

`MultilingualNanoSciFactRetrieval` scores 11 languages (ara deu eng fra ita jpn kor nor por spa
swe), 32,659 samples, main score `ndcg_at_10`. Our Granite-Embedding-97M on the **ANE**, grid
S=512:

| | task score (`ndcg_at_10`) |
| --- | ---: |
| **ours, Granite-Embedding-97M, S=512, ANE** | **0.6551** |
| `intfloat/multilingual-e5-small` | 0.6334 |
| **difference** | **+0.0217** |

⚠️ **Compare task scores, not a plain per-language mean.** The per-language arithmetic mean of our
11 scores is 0.62636; MTEB's task score is a **weighted** aggregate (0.6551). The published
reference is also a task score, so 0.6551 vs 0.6334 is the like-for-like pair. Quoting the plain
mean against a task score would have understated us by 0.03 — the same class of error as mixing
grids in EXP-007.

### Per language

| lang | ndcg@10 | recall@10 | recall@100 |
| --- | ---: | ---: | ---: |
| en | **0.75971** | 0.850 | 0.940 |
| es | 0.68172 | 0.770 | 0.900 |
| **fr** | **0.66304** | **0.760** | **0.900** |
| de | 0.65605 | 0.810 | 0.880 |
| sv | 0.65510 | 0.740 | 0.840 |
| it | 0.60870 | 0.710 | 0.880 |
| pt | 0.59867 | 0.700 | 0.840 |
| ja | 0.58552 | 0.700 | 0.840 |
| ar | 0.57928 | 0.700 | 0.860 |
| ko | 0.55509 | 0.660 | 0.790 |
| no | 0.54703 | 0.670 | 0.860 |

**French is third of eleven and 0.900 at recall@100.** It is not a weak spot, and neither is the
model's multilingual coverage generally.

## What this means for the porting question

The tempting next step was to port a *better* embedder to the ANE — `bge-small` (English-only, so
disqualified), or `mmBERT` (ModernBERT-multilingual, same architecture family as our working
port). **This measurement says: not yet, and maybe not at all.**

- The model we already have **beats the standard multilingual reference** on an 11-language
  retrieval task, from the Neural Engine, at ~2–4 ms per embedding.
- Its weak languages are **Korean, Norwegian, Arabic** — not French. If the corpus is
  French/English, the current model is the right one.
- The earlier English-only conclusion still stands: on English it trails `bge-small`, so a
  **reranker** remains the higher-value improvement — it lifts the *ranking* without changing the
  *model*, and it works in every language at once.

**So the port is deferred, on evidence, not on effort.** If a multilingual corpus later shows a
real gap (e.g. Korean-heavy documents), mmBERT becomes worth the authoring work — and the recipe
transfers.

## The engineering that made this measurable

A 32,659-sample run is ~6× larger than anything tried before, and it exposed a hard limit:

```
CoreAIRuntime/NDArray+Pool.swift:77: Fatal error:
  Failed to allocate storage for NDArray with byteCount: 768, sk: ioSurface, st: float16
```

768 bytes = the 384-d fp16 **output**. The Core AI Python runtime exposes **no release API**, and
outputs are IOSurface-backed, so the pool exhausts under sustained load (~16–24k inferences) and
the process aborts. An in-process model reload does **not** free it — the pool is process-global.

The fix, in `tools/embed-server/embed_server.py`, has three parts and each was needed:

1. **Recycle the process** (`--restart-every`) — the only way to release the pool.
2. **Inherit the listening socket across the exec** (`EMBED_INHERIT_FD` + `socket.fromfd`) — so a
   client never sees a refused connection; its request waits in the backlog.
3. **Recycle *after* the response is flushed**, not before serving — otherwise the in-flight
   request dies. Measured: recycling early gave exactly 3 failures per 10,000, at the recycle
   boundaries.
4. **Threshold, not modulus** — a batched client advances the counter in steps of 64, so
   `_calls % restart_every == 0` never matched and the recycle silently never fired.

Verified: **10,000 requests with no retries, 0 failures, 3 recycles**. This run: **8 recycles,
8 adoptions, 11/11 languages, 639 s**.

## Caveats

- One task, 11 languages, SciFact-style retrieval. Not an MMTEB-wide claim.
- The reference is a single model (`multilingual-e5-small`); `e5-base`/`large` and `bge-m3` have
  no published score on this exact task.
- S=512 grid, and the Nano variant of the task (distilled), so these numbers are **not**
  comparable to the full SciFact numbers in EXP-007.
- The multilingual run took 639 s for 32,659 samples ≈ 51 embeddings/s end-to-end through HTTP.

## Artifacts

- `bench/mteb_retrieval.py` — the evaluation (any OpenAI-compatible endpoint)
- `bench/mteb_french_tasks.py` — the French/multilingual task inventory
- `bench/mteb_multilingual_refs.py` — reference scores, and which tasks have model coverage
- `tools/embed-server/embed_server.py` — the ANE embedder, now safe for long runs
- `~/.cache/mteb/results/granite-embedding-97m-s512/` — raw per-language results

---

## Measurements (generated)

> Generated from `results/measurements.json` by `bench/results_table.py`. **Do not hand-edit** — regenerate.
> Rows appear only when another row is genuinely comparable; `benchmark+split+scope+tiers+metric+unit`
> must agree. See `results/CONSISTENCY-PLAN.md` for why.

| id | model | placement | dtype | seq_len | metric | value | unit | latency_ms | latency_unit | provenance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| granite-97m-ane-s512-ndcg10 | Granite-Embedding-97M | ANE | — | 512 | ndcg_at_10 | 0.6551 | ndcg_at_10 (MTEB task score, weighted) | — | — | ours |
| multilingual-e5-small-ref-ndcg10 | intfloat/multilingual-e5-small | — | — | — | ndcg_at_10 | 0.6334 | ndcg_at_10 (MTEB task score, weighted) | — | — | third-party (published reference score) |
| granite-97m-minus-e5-small-delta | difference (Granite-Embedding-97M, ANE, S=512 − intfloat/multilingual-e5-small) | — | — | — | ndcg_at_10 | 0.0217 | absolute delta over intfloat/multilingual-e5-small (MTEB task score ndcg_at_10) | — | — | ours |
| granite-97m-ane-en-ndcg10 | Granite-Embedding-97M | ANE | — | 512 | ndcg_at_10 | 0.75971 | ndcg@10 | — | — | ours |
| granite-97m-ane-en-recall10 | Granite-Embedding-97M | ANE | — | 512 | recall@10 | 0.85 | recall@10 | — | — | ours |
| granite-97m-ane-en-recall100 | Granite-Embedding-97M | ANE | — | 512 | recall@100 | 0.94 | recall@100 | — | — | ours |
| granite-97m-ane-es-ndcg10 | Granite-Embedding-97M | ANE | — | 512 | ndcg_at_10 | 0.68172 | ndcg@10 | — | — | ours |
| granite-97m-ane-es-recall10 | Granite-Embedding-97M | ANE | — | 512 | recall@10 | 0.77 | recall@10 | — | — | ours |
| granite-97m-ane-es-recall100 | Granite-Embedding-97M | ANE | — | 512 | recall@100 | 0.9 | recall@100 | — | — | ours |
| granite-97m-ane-fr-ndcg10 | Granite-Embedding-97M | ANE | — | 512 | ndcg_at_10 | 0.66304 | ndcg@10 | — | — | ours |
| granite-97m-ane-fr-recall10 | Granite-Embedding-97M | ANE | — | 512 | recall@10 | 0.76 | recall@10 | — | — | ours |
| granite-97m-ane-fr-recall100 | Granite-Embedding-97M | ANE | — | 512 | recall@100 | 0.9 | recall@100 | — | — | ours |
| granite-97m-ane-de-ndcg10 | Granite-Embedding-97M | ANE | — | 512 | ndcg_at_10 | 0.65605 | ndcg@10 | — | — | ours |
| granite-97m-ane-de-recall10 | Granite-Embedding-97M | ANE | — | 512 | recall@10 | 0.81 | recall@10 | — | — | ours |
| granite-97m-ane-de-recall100 | Granite-Embedding-97M | ANE | — | 512 | recall@100 | 0.88 | recall@100 | — | — | ours |
| granite-97m-ane-sv-ndcg10 | Granite-Embedding-97M | ANE | — | 512 | ndcg_at_10 | 0.6551 | ndcg@10 | — | — | ours |
| granite-97m-ane-sv-recall10 | Granite-Embedding-97M | ANE | — | 512 | recall@10 | 0.74 | recall@10 | — | — | ours |
| granite-97m-ane-sv-recall100 | Granite-Embedding-97M | ANE | — | 512 | recall@100 | 0.84 | recall@100 | — | — | ours |
| granite-97m-ane-it-ndcg10 | Granite-Embedding-97M | ANE | — | 512 | ndcg_at_10 | 0.6087 | ndcg@10 | — | — | ours |
| granite-97m-ane-it-recall10 | Granite-Embedding-97M | ANE | — | 512 | recall@10 | 0.71 | recall@10 | — | — | ours |
| granite-97m-ane-it-recall100 | Granite-Embedding-97M | ANE | — | 512 | recall@100 | 0.88 | recall@100 | — | — | ours |
| granite-97m-ane-pt-ndcg10 | Granite-Embedding-97M | ANE | — | 512 | ndcg_at_10 | 0.59867 | ndcg@10 | — | — | ours |
| granite-97m-ane-pt-recall10 | Granite-Embedding-97M | ANE | — | 512 | recall@10 | 0.7 | recall@10 | — | — | ours |
| granite-97m-ane-pt-recall100 | Granite-Embedding-97M | ANE | — | 512 | recall@100 | 0.84 | recall@100 | — | — | ours |
| granite-97m-ane-ja-ndcg10 | Granite-Embedding-97M | ANE | — | 512 | ndcg_at_10 | 0.58552 | ndcg@10 | — | — | ours |
| granite-97m-ane-ja-recall10 | Granite-Embedding-97M | ANE | — | 512 | recall@10 | 0.7 | recall@10 | — | — | ours |
| granite-97m-ane-ja-recall100 | Granite-Embedding-97M | ANE | — | 512 | recall@100 | 0.84 | recall@100 | — | — | ours |
| granite-97m-ane-ar-ndcg10 | Granite-Embedding-97M | ANE | — | 512 | ndcg_at_10 | 0.57928 | ndcg@10 | — | — | ours |
| granite-97m-ane-ar-recall10 | Granite-Embedding-97M | ANE | — | 512 | recall@10 | 0.7 | recall@10 | — | — | ours |
| granite-97m-ane-ar-recall100 | Granite-Embedding-97M | ANE | — | 512 | recall@100 | 0.86 | recall@100 | — | — | ours |
| granite-97m-ane-ko-ndcg10 | Granite-Embedding-97M | ANE | — | 512 | ndcg_at_10 | 0.55509 | ndcg@10 | — | — | ours |
| granite-97m-ane-ko-recall10 | Granite-Embedding-97M | ANE | — | 512 | recall@10 | 0.66 | recall@10 | — | — | ours |
| granite-97m-ane-ko-recall100 | Granite-Embedding-97M | ANE | — | 512 | recall@100 | 0.79 | recall@100 | — | — | ours |
| granite-97m-ane-no-ndcg10 | Granite-Embedding-97M | ANE | — | 512 | ndcg_at_10 | 0.54703 | ndcg@10 | — | — | ours |
| granite-97m-ane-no-recall10 | Granite-Embedding-97M | ANE | — | 512 | recall@10 | 0.67 | recall@10 | — | — | ours |
| granite-97m-ane-no-recall100 | Granite-Embedding-97M | ANE | — | 512 | recall@100 | 0.86 | recall@100 | — | — | ours |
| granite-97m-ane-11lang-mean-ndcg10 | Granite-Embedding-97M | ANE | — | 512 | ndcg_at_10 | 0.62636 | ndcg@10 (plain arithmetic mean over 11 languages; NOT the MTEB task score) | — | — | ours |
