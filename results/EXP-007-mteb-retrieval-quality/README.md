# EXP-007 — is the ANE embedder *good*, or just fast? (MTEB retrieval)

**Question.** EXP-005 got Granite-Embedding-97M onto the Neural Engine at ~2 ms per embedding.
But the model card says outright that its retrieval quality was never measured:

> *"Its retrieval quality relative to those three was **not** measured here: the fixture set below
> is a parity instrument (35 texts, 4 queries, 12 documents), not a benchmark."*

A parity instrument proves the graph is *correct*. It says nothing about whether the vectors are
*useful*. This runs the model against **MTEB**, the field's standard.

**Run:** 2026-09-20 · macOS 27.0 · base M4 · MTEB 2.21.0 · `ndcg_at_10`

---

## Method

MTEB ships `OpenAIAPIEncodeWrapper`, and our embedder is OpenAI-compatible, so no custom protocol
implementation was needed:

```bash
tools/memory-stack/start.sh                      # embed server on :8799
uv run bench/mteb_retrieval.py --tasks SciFact --max-length 128
```

Two integration details worth recording:

- **Pass the BASE url.** MTEB appends `/v1/models` and `/v1/embeddings` itself, so a trailing
  `/v1` yields a 404 on `/v1/v1/models`.
- **`use_chat_template=False`.** The default routes text through a `messages` field, which is a
  **vLLM-only** extension; our server takes the plain `input` field.

## Results

| task | **ours (97M), S=512** | all-MiniLM-L6 (22M) | bge-small (33M) | bge-base (110M) | mpnet-base (110M) |
| --- | ---: | ---: | ---: | ---: | ---: |
| **SciFact** | **0.68546** | 0.64508 | **0.71273** | 0.74345 | 0.65570 |
| **NFCorpus** | **0.29470** | 0.31594 | 0.34264 | 0.37367 | 0.33289 |

Reference values are MTEB's published results, pulled with `mteb.load_results(...)` — same metric,
same splits.

**Verdict: a competent general retriever, not a class-leading one.**

- On **SciFact** it beats `all-MiniLM-L6-v2` by **+0.040** and `all-mpnet-base-v2` by **+0.030**,
  and trails `bge-small-en-v1.5` by 0.027 — a model **one third its size**.
- On **NFCorpus** (clinical/medical) it trails **all four** references, by 0.021 to 0.079.

So it is roughly mpnet-class on general scientific text and weaker on a specialised domain. That
is a useful, unflattering answer to a question the card left open.

## The grid is a real quality/cost dial

The graph is a **fixed grid** and the tokenizer truncates the body to S−2 tokens. SciFact passages
run 150–200 words, so an S=128 build throws away most of every document:

| grid | SciFact nDCG@10 | wall clock for the task |
| --- | ---: | ---: |
| S=128 | 0.65176 | ~17 s |
| **S=512** | **0.68546** | ~86 s |

**+0.034 for ~5× the time.** Worth knowing which way the dial goes, and that the S=128 number is a
floor imposed by the artifact rather than a property of the model.

## Caveats

- **Two tasks.** SciFact and NFCorpus, both English retrieval. Not an MTEB-wide claim.
- **No task prompts.** Granite-Embedding ships with no prompt/instruction prefixes; other models on
  the leaderboard may benefit from theirs, so the comparison is indicative rather than exact.
- **Protocol.** MTEB numbers vary with batch size and harness version; the reference values were
  fetched through the same library, which is the closest available apples-to-apples.
- **NFCorpus nDCG is non-monotonic in k** (`ndcg_at_1` 0.373 > `ndcg_at_10` 0.295 < `ndcg_at_1000`
  0.366). That is a property of a collection with ~38 relevant documents per query, not a bug —
  confirmed against MTEB's own result file, not just our summary parser.
- **The vectors are 384-d and L2-normalized** by the graph; similarity is the dot product.

## What this means for the memory system

The memory stack (EXP-006) does not need a leaderboard retriever. It needs one that is *fast,
free and predictable* — and at ~2 ms on the ANE, embedding is no longer the bottleneck. But the
quality gap is real: `bge-small-en-v1.5` is a third the size and retrieves better on both tasks.

**The obvious next step is not a bigger model — it is a reranker.** Keep the ANE embedder for
candidate generation (where speed matters and recall@100 is 0.93–0.95), then rerank the top-k with
something more accurate. That is the standard two-stage shape, and it plays to what we have.

## Artifacts

- `bench/mteb_retrieval.py` — the evaluation (`uv run`, isolated env)
- `bench/mteb_reference.py` — published reference scores for comparable models
- `bench/mteb_interface.py` — the interface probe whose findings the method section records
- `work/mteb/summary_s{128,512}.json` — the raw scores
- `tools/embed-server/embed_server.py` — the ANE embedder, now grid-aware (`--seq-len`)

---

## Measurements (generated)

> Generated from `results/measurements.json` by `bench/results_table.py`. **Do not hand-edit** — regenerate.
> Rows appear only when another row is genuinely comparable; `benchmark+split+scope+tiers+metric+unit`
> must agree. See `results/CONSISTENCY-PLAN.md` for why.

| id | model | placement | dtype | seq_len | metric | value | unit | latency_ms | latency_unit | provenance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| granite-97m-scifact-s512 | Granite-Embedding-97M | ANE | — | 512 | ndcg_at_10 | 0.68546 | ndcg@10 | — | — | ours |
| minilm-l6-scifact | all-MiniLM-L6 | — | — | — | ndcg_at_10 | 0.64508 | ndcg@10 | — | — | third-party (MTEB) |
| bge-small-scifact | bge-small | — | — | — | ndcg_at_10 | 0.71273 | ndcg@10 | — | — | third-party (MTEB) |
| bge-base-scifact | bge-base | — | — | — | ndcg_at_10 | 0.74345 | ndcg@10 | — | — | third-party (MTEB) |
| mpnet-base-scifact | mpnet-base | — | — | — | ndcg_at_10 | 0.6557 | ndcg@10 | — | — | third-party (MTEB) |
| granite-97m-nfcorpus-s512 | Granite-Embedding-97M | ANE | — | 512 | ndcg_at_10 | 0.2947 | ndcg@10 | — | — | ours |
| minilm-l6-nfcorpus | all-MiniLM-L6 | — | — | — | ndcg_at_10 | 0.31594 | ndcg@10 | — | — | third-party (MTEB) |
| bge-small-nfcorpus | bge-small | — | — | — | ndcg_at_10 | 0.34264 | ndcg@10 | — | — | third-party (MTEB) |
| bge-base-nfcorpus | bge-base | — | — | — | ndcg_at_10 | 0.37367 | ndcg@10 | — | — | third-party (MTEB) |
| mpnet-base-nfcorpus | mpnet-base | — | — | — | ndcg_at_10 | 0.33289 | ndcg@10 | — | — | third-party (MTEB) |



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

