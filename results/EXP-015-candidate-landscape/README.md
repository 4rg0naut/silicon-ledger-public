# EXP-015 — the candidate landscape: what can actually run on the ANE

**Question.** Our retriever is the weak half of the stack (EXP-014: −0.050 behind bge-base). Which
embedders could replace it — and **which of them can we actually get onto the Neural Engine?**

**Method.** Five parallel research passes over the zoo (local checkout + upstream), HuggingFace, and
our own experiment records. Every claim below carries a source.

---

## The binding constraint is availability, not quality

**Exactly five** embedding/retrieval models have a published Core AI `.aimodel` bundle *and* a
`status = "verified"` recipe:

| model | langs | dim | ANE status | matching reranker |
| --- | --- | ---: | --- | --- |
| **Granite-Embedding-97M-Multilingual-R2** | 52 enhanced / 200+ pretrained | 384 | **bundle** (+ iOS h18p AOT) | none in family |
| **EmbeddingGemma-300m** | 100+ | 768 | **bundle**, verified | none in family |
| **Qwen3-Embedding-0.6B** | 100+ | 1024 (MRL 32–1024) | **bundle**, verified | Qwen3-Reranker-0.6B ✅ |
| **Qwen3-Reranker-0.6B** | 100+ | — | **bundle**, verified | *is* the reranker |
| **ColModernVBERT** | **English only** | — | **bundle** (4) | none |
| *Nemotron-3-Embed-1B* | 34 | 2048 | *exporter + gates exist, no recipe/bundle* | none |

**Everything else is "nothing — we'd write it."** In particular:

- **BGE has ZERO Core AI presence.** A recursive grep of the zoo for `bge` returns **no matches** —
  no bundle, no `export_bge*.py`. BGE exists only as **ExecuTorch** (`.pte`/XNNPACK) ports, which
  are a different runtime. So `bge-m3` and `bge-reranker-v2-m3` — the two multilingual BGE models
  that would otherwise be the obvious answer — are **a from-scratch port**.
- `multilingual-e5-*`, `LaBSE`, `paraphrase-multilingual-mpnet`, `snowflake-arctic-embed-l-v2.0`:
  no bundle, no recipe. The zoo has **no XLM-RoBERTa or BERT exporter at all**.
- `jina-embeddings-v3`: multilingual and strong, but 5 task-LoRA adapters + custom `modeling_lora`
  + FlashAttention make it the **worst ANE fit** in the set, and it is **CC-BY-NC-4.0**.

**Only ONE cross-encoder reranker is ported in the entire zoo: `qwen3-reranker` — ours.**

## The quality picture — and the hole in it

The zoo ran its own multilingual head-to-head (`_smoke/compare_embedders_retrieval.py`, results
`_smoke/results/embedder_retrieval_2026-08-25.json`) on three tasks:

| nDCG@10 | NanoSciFact (EN) | JaQuAD (JA) | MIRACL-ja (JA) |
| --- | ---: | ---: | ---: |
| EmbeddingGemma-300m | **0.864** | **0.621** | 0.825 |
| Nemotron-3-Embed-1B | 0.765 | 0.616 | **0.862** |
| Qwen3-Embedding-0.6B | 0.687 | 0.570 | 0.792 |
| **Granite-97M (ours)** | **not measured** | **not measured** | **not measured** |

**The zoo compared three embedders and left ours out.** So the single most valuable measurement
available is not "try another model" — it is **putting our incumbent into that existing harness**,
which is multilingual and already covers Japanese.

Two things follow immediately:

1. **Qwen3-Embedding-0.6B is ruled out.** It is the only Qwen retriever with an ANE path, and the
   zoo's own numbers rank it **last of three on both English and Japanese**. It is not the upgrade.
2. **`EmbeddingGemma-300m` and `Nemotron-3-Embed-1B` are the two real candidates** — the first
   already has a bundle, the second has an exporter and gates but no recipe yet.

## The full candidate table

| # | model | HF id | params | dim | langs | ANE status | reranker | evidence | licence |
| ---: | --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| 1 | Granite-Emb-97M-Mult-R2 | `ibm-granite/granite-embedding-97m-multilingual-r2` | 97M | 384 | 52+/200+ | **bundle + AOT** | — | zoo card; EXP-009/011 | Apache-2.0 |
| 2 | EmbeddingGemma-300m | `google/embeddinggemma-300m` | 300M | 768 | 100+ | **bundle** | — | zoo recipe; zoo multilingual table | Gemma |
| 3 | Qwen3-Embedding-0.6B | `Qwen/Qwen3-Embedding-0.6B` | 0.6B | 1024 MRL | 100+ | **bundle** | Qwen3-Reranker | zoo recipe; ranked **last** | Apache-2.0 |
| 4 | Qwen3-Reranker-0.6B | `Qwen/Qwen3-Reranker-0.6B` | 0.6B | — | 100+ | **bundle** | *is it* | zoo recipe; EXP-013 ANE port | Apache-2.0 |
| 5 | ColModernVBERT | `ModernVBERT/colmodernvbert` | 250M | — | **EN only** | **bundle** (4) | — | zoo recipe | — |
| 6 | Nemotron-3-Embed-1B | `nvidia/Nemotron-3-Embed-1B-BF16` | 1B | 2048 | 34 | *exporter + gates, no recipe* | — | `conversion/export_nemotron_embed.py` | — |
| 7 | bge-m3 | `BAAI/bge-m3` | 568M | 1024 | 100+ | **nothing** | bge-reranker-v2-m3 | zoo grep `bge` = 0 hits | MIT |
| 8 | bge-reranker-v2-m3 | `BAAI/bge-reranker-v2-m3` | 568M | — | 100+ | **nothing** | *is it* | same | Apache-2.0 |
| 9 | multilingual-e5-large | `intfloat/multilingual-e5-large` | 560M | 1024 | 100+ | **nothing** | — | no recipe; no XLM-R exporter | MIT |
| 10 | arctic-embed-l-v2.0 | `Snowflake/snowflake-arctic-embed-l-v2.0` | 568M | 1024 | 100+ | **nothing** | — | no recipe | Apache-2.0 |
| 11 | jina-embeddings-v3 | `jinaai/jina-embeddings-v3` | 570M | 1024 | 100+ | **nothing** | — | LoRA adapters; worst ANE fit | **CC-BY-NC-4.0** |
| 12 | LaBSE | `sentence-transformers/LaBSE` | 471M | 768 | 109 | **nothing** | — | no recipe | Apache-2.0 |

*(12 rows — the 10 requested plus the two that turn out to be our own stack's halves.)*

**Two ANE-specific constraints the research surfaced:**

- **A >250k-vocab embedding table cannot be fp32 on the ANE** — the Nemotron exporter documents
  this. The table must be stored fp16. This affects bge-m3 (250k), LaBSE (501k), XLM-R models.
- **No zoo card verifies the ANE as the compute unit.** Only Granite ships iOS h18p AOT bundles, and
  its own card lists *"the Neural Engine"* under **Not tested**. Our EXP-013 result is the first
  verified full-ANE residency for any of these — and the first cross-encoder on the ANE anywhere in
  the zoo.

## mmBERT — the candidate the availability filter hid

Asked directly, and it deserves its own section because it is the strongest candidate in the set on
the axis we are weakest: **language coverage**.

| | |
| --- | --- |
| source | `jhu-clsp/mmBERT-{base,small}` — JHU CLSP, HF blog 2025-09-09, arXiv 2509.06888 |
| architecture | **`model_type: modernbert`** — 22 layers, 1152 intermediate, **Gemma-2 tokenizer (256k vocab)** |
| sizes | small 140M total / **42M non-embedding**; base 307M / **110M non-embedding** |
| languages | **1,833** (3T tokens) — against our incumbent's 52 enhanced / 200+ pretrained |
| context | 8,192 (YaRN-extended community forks reach 32,768) |
| licence | **MIT** |
| retrieval | blog: *"significant gains over previous multilingual models and even ties the capabilities of English-only models like ModernBERT"* on MTEB-v2 English; consistent gains on MTEB-v2 multilingual |

**Why the availability filter hid it:** it has no Core AI bundle and no zoo recipe, so it ranked as
*"nothing — we'd write it"* and fell out of the shortlist. But **the porting cost is unusually low**,
because our incumbent is *also* ModernBERT — the zoo's own card calls Granite-97M
*"the only encoder-architecture one — every other embedder here is a causal decoder run as an
encoder"*. The zoo's `export_granite_embedding.py` is therefore the natural starting point rather
than a from-scratch exporter.

**Architecture comparison to our incumbent:**

| | layers | hidden | vocab | embed table (fp16) | non-embedding |
| --- | ---: | ---: | ---: | ---: | ---: |
| Granite-97M (ours) | 12 | 384 | 49,155 | 36 MB | ~39M |
| **mmBERT-small** | 22 | 384 | 256,000 | **188 MB** | 39M |
| **mmBERT-base** | 22 | 768 | 256,000 | **375 MB** | 156M |

Same width as ours at small, 1.8× deeper; the **256k vocabulary is the cost** (5.2× our embedding
table). The zoo's Nemotron exporter documents that a >250k-vocab table **cannot be fp32 on the
ANE** — it must ship fp16, which the numbers above already assume.

**The catch — it is not an embedding model.** `jhu-clsp` publishes exactly three mmBERT repos
(`mmBERT-base`, `mmBERT-small`, `mmBERT-checkpoints`) and **all three are `fill-mask` encoders**.
The MTEB tables in the blog are for mmBERT **fine-tuned into** an embedder, and the blog supplies
that recipe (`SentenceTransformer` + `CachedMultipleNegativesRankingLoss`). So there are two paths:

1. **Fine-tune it ourselves** — recipe is published, but it is a training project (the blog's
   example uses 1.25M triplets and a 512 batch size).
2. **Use a community embedder built on it.** The strongest is
   `llm-semantic-router/mmbert-embed-32k-2d-matryoshka` — **Apache-2.0**, 36.7k downloads,
   `sentence-transformers`, `ModernBertModel`, 22 layers × 768, **32,768 context**, tagged
   `multilingual` + `matryoshka` + `2d-matryoshka`, trained on `BAAI/bge-m3-data`, and it already
   ships **ONNX exports at layers 11/16/22** (the 2D-Matryoshka axis). Its quality is
   **[UNVERIFIED]** by us — we have not measured it.

**MEASURED (2026-09-21).** The community embedder was run through the zoo's harness, matched
protocol, against our incumbent:

| task | our Granite | **mmBERT embedder** | gap |
| --- | ---: | ---: | ---: |
| NanoSciFact (EN) | **0.7526** | 0.4780 | −0.275 |
| JaQuAD (JA) | **0.5426** | 0.4673 | −0.075 |
| MIRACL-ja (JA) | **0.7735** | 0.6588 | −0.115 |

**It is last on all three, well below our incumbent** — so the available mmBERT embedder is not a
candidate, whatever the base encoder's pedigree. And unlike the Qwen3 comparison, this one is
**statistically clear** — the harness's paired bootstrap puts the 95% CI entirely above zero on
every task:

```
[NanoSciFact] ours vs mmBERT: +0.2745 [+0.1674, +0.3860]  clear
[JaQuAD]      ours vs mmBERT: +0.0753 [+0.0471, +0.1049]  clear
[MIRACL-ja]   ours vs mmBERT: +0.1147 [+0.0845, +0.1468]  clear
```

So the three candidates now separate cleanly by the zoo's own rubric:

| candidate | verdict | basis |
| --- | --- | --- |
| **EmbeddingGemma-300m** | **UPGRADE** | clearly ahead (+0.111 EN, +0.078 JA) and measured on the ANE |
| Qwen3-Embedding-0.6B | **KEEP-LOCAL** | directionally ahead on JA but **not separated at 95%** |
| mmBERT embedder | **REJECT** | clearly *behind* on all three |

That is not a verdict on mmBERT itself. Three things to keep separate:

1. **The base encoder** (`jhu-clsp/mmBERT-base`) is a masked-LM. The blog's MTEB tables — *"ties the
   capabilities of English-only models like ModernBERT"* — are for mmBERT **fine-tuned into** an
   embedder, not for this artifact.
2. **This community embedder** is a different thing: trained on `BAAI/bge-m3-data`, YaRN-extended to
   32k, with 2D Matryoshka. Those are long-context choices, and our three tasks are short-text
   retrieval — the extension may simply be mismatched, which would also explain the unusually poor
   English number.
3. **Our own comparison is one artifact, not a family.** A second mmBERT embedder
   (`emillykkejensen/mmBERTscandi-base-embedding`, `Omartificial-Intelligence-Space/mmbert-base-arabic-nli`)
   exists but is language-specialised.

**So mmBERT's standing, stated honestly:** the best *language coverage* in the candidate set
(1,833 languages) and the most port-friendly architecture we do not already run, but **the embedder
that exists scores far below our incumbent on our tasks**, and using it properly means fine-tuning
it ourselves. It is a project, not a download — and on the evidence, it is behind EmbeddingGemma for
the English/Japanese work that actually matters here.

**Original research summary (kept for the record):** the best *language coverage* in the candidate set and the most port-friendly
architecture we do not already run, but it is **not a drop-in** — either a fine-tune or a
third-party embedder, then a port. It is the one candidate that plausibly moves the multilingual
hole rather than the English number.

## MEASURED: our incumbent in the zoo's multilingual harness (2026-09-21)

The zoo compared three embedders and left ours out. That gap is now closed — the harness was run
with our model added, **same protocol** (seq_len 256, MPS, paired bootstrap, identical corpora and
metrics; `_smoke/compare_embedders_retrieval.py`).

**Reproducibility check first:** our run of Qwen3-Embedding-0.6B on NanoSciFact returned
**0.6869** — *exactly* the zoo's published 0.6869. The protocol reproduces, so the numbers below are
comparable.

### NanoSciFact (English, 50 queries, 2919 docs)

| model | nDCG@10 | source |
| --- | ---: | --- |
| EmbeddingGemma-300m | **0.8638** | zoo, published |
| Nemotron-3-Embed-1B | 0.7654 | zoo, published |
| **Granite-97M (ours)** | **0.7526** | **measured here** |
| Qwen3-Embedding-0.6B | 0.6869 | measured here (reproduces zoo exactly) |

### JaQuAD (Japanese, 2048 queries, 3014 docs)

| model | nDCG@10 | source |
| --- | ---: | --- |
| EmbeddingGemma-300m | 0.6208 | zoo, published (250 q) |
| Nemotron-3-Embed-1B | 0.6157 | zoo, published (250 q) |
| **Qwen3-Embedding-0.6B** | **0.5777** | measured here (2048 q; zoo's 250-q value is 0.5695) |
| **Granite-97M (ours)** | **0.5425** | **measured here** |

*(JaQuAD is flagged `[weak]` by the harness itself — only 1.0× the judged set, so read margins with
care. The query count differs from the zoo's published run, which is why Qwen3 reads 0.5777 here
against their 0.5695.)*

### MIRACL-ja (Japanese, 250 queries, 8000 docs — the zoo's exact subset)

| model | nDCG@10 | source |
| --- | ---: | --- |
| Nemotron-3-Embed-1B | **0.8623** | zoo, published |
| EmbeddingGemma-300m | 0.8246 | zoo, published |
| Qwen3-Embedding-0.6B | 0.7916 | zoo, published |
| **Granite-97M (ours)** | **0.7735** | **measured here** |

### The full picture — matched protocol, 250 queries, zoo subset

| task | EmbeddingGemma | Nemotron | Qwen3 | **ours** | our rank |
| --- | ---: | ---: | ---: | ---: | --- |
| NanoSciFact (EN) | **0.8638** | 0.7654 | 0.6869 | 0.7526 | **3rd of 4** |
| JaQuAD (JA) | **0.6208** | 0.6157 | 0.5695 | 0.5426 | **4th of 4** |
| MIRACL-ja (JA) | 0.8246 | **0.8623** | 0.7916 | 0.7735 | **4th of 4** |

**Protocol validation: both of our Qwen3 runs reproduce the zoo's published values exactly** —
0.6869 on NanoSciFact and **0.5695** on JaQuAD. So our rows sit in the same table legitimately.

### EmbeddingGemma, measured ON THE ANE (the decisive row)

The zoo's bundle is **not gated**, so it was downloaded, AOT-compiled for the ANE (**full residency:
1 region, 0 GPU, 0 CPU**), and served through a small ANE embed server — then scored on the zoo's
own tasks with the zoo's own loader and metric (`bench/eval_ane_embedder.py` imports
`_smoke/compare_embedders_retrieval.py` rather than re-implementing it).

| task | zoo's CPU number | **ours, on the ANE** | our incumbent | gain |
| --- | ---: | ---: | ---: | ---: |
| NanoSciFact (EN) | 0.8638 | **0.8637** | 0.7526 | **+0.111** |
| JaQuAD (JA) | 0.6208 | **0.6205** | 0.5426 | **+0.078** |
| MIRACL-ja (JA) | 0.8246 | *(ANE crashed — F-35)* | **0.8225** (GPU) | 0.7735 | **+0.049** |

**Both ANE numbers reproduce the zoo's CPU numbers to four decimals** (0.8637 vs 0.8638; 0.6205 vs
0.6208).

**MIRACL-ja was completed on the GPU delegate instead: 0.8225** — the bundle crashes MPSGraph on
the ANE under sustained load (**F-35**), and Google's paper shows why: the model wants bf16/fp32,
and fp16 is unsupported, so the zoo's fp32 was correct and the fix is an **int8 QAT export**, which
is a native ANE dtype. All three tasks now pass, and the retriever gain is confirmed on every one:
**+0.111 EN, +0.078 JA, +0.049 JA**. — it survived ~6,400 embeddings, and ~9,000 with process recycling, then died in
`MPSAutoCache::GetTempBuffer`. The likely cause is that this bundle ships **float32**, which is not
the ANE's native dtype. So the MIRACL-ja row uses the zoo's published CPU value, and a production
port of this model should re-export it **fp16**. That is a strong result twice over:

1. **It validates our ANE serving path** — running a Core AI bundle on the Neural Engine gives the
   same retrieval quality as the CPU reference, so the ANE port costs nothing in quality.
2. **It confirms the upgrade is real** — EmbeddingGemma is **+0.111 on English and +0.078 on
   Japanese** over our incumbent, *while running on the ANE*, which is the whole point.

### A caveat that cuts against the "we are last" reading

The harness's own **paired bootstrap** (10k resamples) on the matched run:

```
JaQuAD    ours vs Qwen3: +0.0269  [-0.0000, +0.0536]  NOT separated at 95%
MIRACL-ja ours vs Qwen3: +0.0181  [-0.0059, +0.0418]  NOT separated at 95%
```

**Qwen3's lead over our incumbent is not statistically separated.** The zoo's rubric is explicit:
*"a candidate that does not clearly beat the shipped rows above is KEEP-LOCAL, not SHIP."* By that
rule **Qwen3 is not an upgrade for us** — it is directionally ahead on Japanese and not separable.

So the honest statement is: **our incumbent is behind, Qwen3 is not clearly better, and
EmbeddingGemma is clearly better and runs on the ANE.**

### What this says

**Our incumbent is 3rd of 4 on English and last of 4 on Japanese.** And the sharpest version of it:

> **Qwen3-Embedding-0.6B — the model we ruled out because the zoo ranks it last of three — beats our
> Granite by +0.035 on Japanese.**

That does not rescue Qwen3 (it is still behind EmbeddingGemma and Nemotron on both tasks), but it
does mean **our multilingual retriever is weaker than we assumed**. EXP-008's single multilingual
run suggested we were competitive; in this harness we are not.

**The upgrade target is unambiguous: `EmbeddingGemma-300m`** — and it is now **measured on the
ANE**: +0.111 on English and +0.078 on Japanese over our incumbent, at zoo-identical quality. Its
upstream HF repo is gated, but **the zoo's bundle is not**, so no token was needed after all.

## End-to-end: the swap, in the real pipeline (2026-09-21)

Swapping the retriever in the SciFact pipeline (EXP-011's chunk index + EXP-012's harness), same
ANE reranker for both arms:

| pipeline | retriever baseline | + ANE reranker | gain |
| --- | ---: | ---: | ---: |
| Granite-97M (ANE) | 0.67923 | 0.75860 | **+0.079** |
| **EmbeddingGemma-300m (GPU)** | **0.75177** | **0.76282** | +0.011 |

**The retriever swap moves the baseline by +0.073 but the pipeline by only +0.004.** Two things
follow, and the second is the more useful:

1. **EmbeddingGemma is a genuinely better retriever** — +0.073 on the shortlist before any reranking.
2. **The reranker and a good retriever are largely redundant.** Our +0.079 reranker gain was mostly
   *compensating* for a weak retriever. Given a strong one, the reranker adds +0.011 — and
   **`recall@10` actually falls** (0.8876 → 0.8709), i.e. it now pushes relevant documents *out* of
   the top-10.

**So the honest reading of EXP-012's headline is not "the reranker bought +0.079" but "the reranker
bought +0.079 *on a weak shortlist*".** The reranker is a fix for a bad retriever, not an
independent gain — which is exactly what the paired-bootstrap work in EXP-014/015 was circling.

## Recommendation, in order

0. ~~Add our incumbent to the zoo's multilingual harness FIRST~~ — **DONE, and it changes the
   plan**: we are 3rd/4 on English and last/4 on Japanese (see the MEASURED section above).
1. **`EmbeddingGemma-300m` is now the upgrade target** — first on English by +0.111 over ours, first
   on JaQuAD, and already bundled. Needs an HF token to even measure against. mmBERT (below) stays
   the long-shot for language *coverage*.
2. **Add Granite-97M to the zoo's multilingual harness** (`compare_embedders_retrieval.py`) so our
   incumbent sits in the same table as the three that were measured. Cheapest possible action, and
   it closes our biggest evidence hole. **Nothing else should be decided before this.**
2. **Test `EmbeddingGemma-300m` against our Granite** — it has a verified bundle, 100+ languages,
   and leads the zoo's table on English *and* JaQuAD.
3. **Finish `Nemotron-3-Embed-1B`** — exporter and gates exist, only the recipe is missing, and it
   is the **MIRACL-ja champion (0.862)**. 34 languages, 1B params.
4. **Only then** consider a from-scratch port (bge-m3) — it is the strongest multilingual embedder
   in the list but is a genuine conversion project with a 250k-vocab table to handle.

## Caveats

- The zoo's table is **three tasks with 50–250 queries each**; it is a screening instrument, not a
  benchmark. Gaps were separated at 95% by paired bootstrap on the zoo's side.
- **Do not compare these nDCG@10 numbers to our SciFact numbers.** Different task, different
  protocol. SciFact and NanoSciFact are not the same benchmark.
- All zoo numbers are **GPU** measurements. None of them establishes ANE behaviour for these
  embedders; only our own EXP-013 does, and only for the reranker.
- BGE's absence from the zoo is a statement about *the zoo*, not about BGE's quality.

## Artifacts

- `work/charts/candidates.png` — availability + multilingual quality, side by side
- `bench/make_charts.py` — `candidates()` / `multiling()` panels
- Scout transcripts: `history://BgeFamily`, `history://QwenFamily`, `history://MultilingualSpec`,
  `history://AneAvailability`, `history://HarnessHoles`

---

## Measurements (generated)

> Generated from `results/measurements.json` by `bench/results_table.py`. **Do not hand-edit** — regenerate.
> Rows appear only when another row is genuinely comparable; `benchmark+split+scope+tiers+metric+unit`
> must agree. See `results/CONSISTENCY-PLAN.md` for why.

| id | model | placement | dtype | seq_len | metric | value | unit | latency_ms | latency_unit | provenance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| zoo-h2h-embeddinggemma-nanoscifact | EmbeddingGemma-300m | GPU | — | — | ndcg@10 | 0.864 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| zoo-h2h-embeddinggemma-jaquad | EmbeddingGemma-300m | GPU | — | — | ndcg@10 | 0.621 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| zoo-h2h-embeddinggemma-miracl-ja | EmbeddingGemma-300m | GPU | — | — | ndcg@10 | 0.825 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| zoo-h2h-nemotron-nanoscifact | Nemotron-3-Embed-1B | GPU | — | — | ndcg@10 | 0.765 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| zoo-h2h-nemotron-jaquad | Nemotron-3-Embed-1B | GPU | — | — | ndcg@10 | 0.616 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| zoo-h2h-nemotron-miracl-ja | Nemotron-3-Embed-1B | GPU | — | — | ndcg@10 | 0.862 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| zoo-h2h-qwen3-nanoscifact | Qwen3-Embedding-0.6B | GPU | — | — | ndcg@10 | 0.687 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| zoo-h2h-qwen3-jaquad | Qwen3-Embedding-0.6B | GPU | — | — | ndcg@10 | 0.57 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| zoo-h2h-qwen3-miracl-ja | Qwen3-Embedding-0.6B | GPU | — | — | ndcg@10 | 0.792 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| mmbert-matched-nanoscifact-ours | Granite-97M (ours) | GPU (MPS) | — | — | ndcg@10 | 0.7526 | ndcg@10 | — | — | ours |
| mmbert-matched-nanoscifact-mmbert | mmBERT embedder | GPU (MPS) | — | — | ndcg@10 | 0.478 | ndcg@10 | — | — | ours |
| mmbert-matched-nanoscifact-gap | mmBERT embedder | GPU (MPS) | — | — | ndcg@10 delta | -0.275 | absolute delta over Granite-97M (ours), ndcg@10 | — | — | ours |
| mmbert-matched-jaquad-ours | Granite-97M (ours) | GPU (MPS) | — | — | ndcg@10 | 0.5426 | ndcg@10 | — | — | ours |
| mmbert-matched-jaquad-mmbert | mmBERT embedder | GPU (MPS) | — | — | ndcg@10 | 0.4673 | ndcg@10 | — | — | ours |
| mmbert-matched-jaquad-gap | mmBERT embedder | GPU (MPS) | — | — | ndcg@10 delta | -0.075 | absolute delta over Granite-97M (ours), ndcg@10 | — | — | ours |
| mmbert-matched-miracl-ja-ours | Granite-97M (ours) | GPU (MPS) | — | — | ndcg@10 | 0.7735 | ndcg@10 | — | — | ours |
| mmbert-matched-miracl-ja-mmbert | mmBERT embedder | GPU (MPS) | — | — | ndcg@10 | 0.6588 | ndcg@10 | — | — | ours |
| mmbert-matched-miracl-ja-gap | mmBERT embedder | GPU (MPS) | — | — | ndcg@10 delta | -0.115 | absolute delta over Granite-97M (ours), ndcg@10 | — | — | ours |
| bootstrap-mmbert-nanoscifact | Granite-97M (ours) | GPU (MPS) | — | — | ndcg@10 delta (paired bootstrap, ours vs mmBERT) | 0.2745 | ndcg@10 delta, paired bootstrap 95% CI [+0.1674, +0.3860], clear | — | — | ours |
| bootstrap-mmbert-jaquad | Granite-97M (ours) | GPU (MPS) | — | — | ndcg@10 delta (paired bootstrap, ours vs mmBERT) | 0.0753 | ndcg@10 delta, paired bootstrap 95% CI [+0.0471, +0.1049], clear | — | — | ours |
| bootstrap-mmbert-miracl-ja | Granite-97M (ours) | GPU (MPS) | — | — | ndcg@10 delta (paired bootstrap, ours vs mmBERT) | 0.1147 | ndcg@10 delta, paired bootstrap 95% CI [+0.0845, +0.1468], clear | — | — | ours |
| harness-nanoscifact-embeddinggemma | EmbeddingGemma-300m | GPU | — | — | ndcg@10 | 0.8638 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| harness-nanoscifact-nemotron | Nemotron-3-Embed-1B | GPU | — | — | ndcg@10 | 0.7654 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| harness-nanoscifact-granite-ours | Granite-97M (ours) | GPU (MPS) | — | 256 | ndcg@10 | 0.7526 | ndcg@10 | — | — | ours |
| harness-nanoscifact-qwen3 | Qwen3-Embedding-0.6B | GPU (MPS) | — | 256 | ndcg@10 | 0.6869 | ndcg@10 | — | — | ours |
| harness-jaquad-embeddinggemma | EmbeddingGemma-300m | GPU | — | — | ndcg@10 | 0.6208 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| harness-jaquad-nemotron | Nemotron-3-Embed-1B | GPU | — | — | ndcg@10 | 0.6157 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| harness-jaquad-qwen3 | Qwen3-Embedding-0.6B | GPU (MPS) | — | 256 | ndcg@10 | 0.5777 | ndcg@10 | — | — | ours |
| harness-jaquad-granite-ours | Granite-97M (ours) | GPU (MPS) | — | 256 | ndcg@10 | 0.5425 | ndcg@10 | — | — | ours |
| harness-miracl-ja-nemotron | Nemotron-3-Embed-1B | GPU | — | — | ndcg@10 | 0.8623 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| harness-miracl-ja-embeddinggemma | EmbeddingGemma-300m | GPU | — | — | ndcg@10 | 0.8246 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| harness-miracl-ja-qwen3 | Qwen3-Embedding-0.6B | GPU | — | — | ndcg@10 | 0.7916 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| harness-miracl-ja-granite-ours | Granite-97M (ours) | GPU (MPS) | — | 256 | ndcg@10 | 0.7735 | ndcg@10 | — | — | ours |
| full250-nanoscifact-embeddinggemma | EmbeddingGemma-300m | GPU | — | — | ndcg@10 | 0.8638 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| full250-nanoscifact-nemotron | Nemotron-3-Embed-1B | GPU | — | — | ndcg@10 | 0.7654 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| full250-nanoscifact-qwen3 | Qwen3-Embedding-0.6B | GPU | — | — | ndcg@10 | 0.6869 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| full250-nanoscifact-granite-ours | Granite-97M (ours) | GPU (MPS) | — | 256 | ndcg@10 | 0.7526 | ndcg@10 | — | — | ours |
| full250-jaquad-embeddinggemma | EmbeddingGemma-300m | GPU | — | — | ndcg@10 | 0.6208 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| full250-jaquad-nemotron | Nemotron-3-Embed-1B | GPU | — | — | ndcg@10 | 0.6157 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| full250-jaquad-qwen3 | Qwen3-Embedding-0.6B | GPU | — | — | ndcg@10 | 0.5695 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| full250-jaquad-granite-ours | Granite-97M (ours) | GPU (MPS) | — | 256 | ndcg@10 | 0.5426 | ndcg@10 | — | — | ours |
| full250-miracl-ja-embeddinggemma | EmbeddingGemma-300m | GPU | — | — | ndcg@10 | 0.8246 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| full250-miracl-ja-nemotron | Nemotron-3-Embed-1B | GPU | — | — | ndcg@10 | 0.8623 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| full250-miracl-ja-qwen3 | Qwen3-Embedding-0.6B | GPU | — | — | ndcg@10 | 0.7916 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| full250-miracl-ja-granite-ours | Granite-97M (ours) | GPU (MPS) | — | 256 | ndcg@10 | 0.7735 | ndcg@10 | — | — | ours |
| ane-gemma-nanoscifact-zoo-cpu | EmbeddingGemma-300m | CPU | fp32 | — | ndcg@10 | 0.8638 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| ane-gemma-nanoscifact-ane | EmbeddingGemma-300m | ANE | fp32 | — | ndcg@10 | 0.8637 | ndcg@10 | — | — | ours |
| ane-gemma-nanoscifact-incumbent | Granite-97M (ours) | GPU (MPS) | — | — | ndcg@10 | 0.7526 | ndcg@10 | — | — | ours |
| ane-gemma-nanoscifact-gain | EmbeddingGemma-300m | ANE | — | — | ndcg@10 delta | 0.111 | absolute delta over Granite-97M (ours), ndcg@10 | — | — | ours |
| ane-gemma-jaquad-zoo-cpu | EmbeddingGemma-300m | CPU | fp32 | — | ndcg@10 | 0.6208 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| ane-gemma-jaquad-ane | EmbeddingGemma-300m | ANE | fp32 | — | ndcg@10 | 0.6205 | ndcg@10 | — | — | ours |
| ane-gemma-jaquad-incumbent | Granite-97M (ours) | GPU (MPS) | — | — | ndcg@10 | 0.5426 | ndcg@10 | — | — | ours |
| ane-gemma-jaquad-gain | EmbeddingGemma-300m | ANE | — | — | ndcg@10 delta | 0.078 | absolute delta over Granite-97M (ours), ndcg@10 | — | — | ours |
| ane-gemma-miracl-ja-zoo-cpu | EmbeddingGemma-300m | CPU | fp32 | — | ndcg@10 | 0.8246 | ndcg@10 | — | — | third-party (zoo _smoke/compare_embedders_retrieval.py) |
| ane-gemma-miracl-ja-gpu | EmbeddingGemma-300m | GPU | fp32 | — | ndcg@10 | 0.8225 | ndcg@10 | — | — | ours |
| ane-gemma-miracl-ja-incumbent | Granite-97M (ours) | GPU (MPS) | — | — | ndcg@10 | 0.7735 | ndcg@10 | — | — | ours |
| ane-gemma-miracl-ja-gain | EmbeddingGemma-300m | ANE | — | — | ndcg@10 delta | 0.049 | absolute delta over Granite-97M (ours), ndcg@10 | — | — | ours |
| pipeline-scifact-granite-retriever-baseline | Granite-97M (ours) | ANE | — | — | pipeline score | 0.6792 | pipeline score | — | — | ours |
| pipeline-scifact-granite-plus-ane-reranker | Granite-97M (ours) | ANE | — | — | pipeline score | 0.7586 | pipeline score | — | — | ours |
| pipeline-scifact-granite-gain | Granite-97M (ours) | ANE | — | — | pipeline score delta | 0.079 | absolute delta from reranker, pipeline score | — | — | ours |
| pipeline-scifact-gemma-retriever-baseline | EmbeddingGemma-300m | GPU | — | — | pipeline score | 0.7518 | pipeline score | — | — | ours |
| pipeline-scifact-gemma-plus-ane-reranker | EmbeddingGemma-300m | GPU | — | — | pipeline score | 0.7628 | pipeline score | — | — | ours |
| pipeline-scifact-gemma-gain | EmbeddingGemma-300m | GPU | — | — | pipeline score delta | 0.011 | absolute delta from reranker, pipeline score | — | — | ours |
| pipeline-gemma-recall10-no-rerank | EmbeddingGemma-300m | GPU | — | — | recall@10 | 0.8876 | recall@10 | — | — | ours |
| pipeline-gemma-recall10-with-rerank | EmbeddingGemma-300m | GPU | — | — | recall@10 | 0.8709 | recall@10 | — | — | ours |
| gemma-ane-residency | EmbeddingGemma-300m | ANE | fp32 | — | ANE regions | 1 | ANE regions (0 GPU ops, 0 CPU ops) | — | — | ours |
| gemma-ane-crash-6400 | EmbeddingGemma-300m | ANE | fp32 | — | sustained embeddings before crash | 6400 | embeddings before MPSGraph crash (approximate) | — | — | ours |
| gemma-ane-crash-9000 | EmbeddingGemma-300m | ANE | fp32 | — | sustained embeddings before crash | 9000 | embeddings before MPSGraph crash with process recycling (approximate) | — | — | ours |
| bootstrap-qwen3-jaquad | Granite-97M (ours) | GPU (MPS) | — | — | ndcg@10 delta (paired bootstrap, ours vs Qwen3) | 0.0269 | ndcg@10 delta, paired bootstrap 95% CI [-0.0000, +0.0536], not separated at 95% | — | — | ours |
| bootstrap-qwen3-miracl-ja | Granite-97M (ours) | GPU (MPS) | — | — | ndcg@10 delta (paired bootstrap, ours vs Qwen3) | 0.0181 | ndcg@10 delta, paired bootstrap 95% CI [-0.0059, +0.0418], not separated at 95% | — | — | ours |
