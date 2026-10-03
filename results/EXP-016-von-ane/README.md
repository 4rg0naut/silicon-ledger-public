# EXP-016 — Von-1.0 on the Neural Engine: a decision model, ported

**Question.** Von (`wfzyx/von`) is a **non-autoregressive System One decision model** — one forward
pass, no KV cache, no token-by-token decoding, ~18 ms. Its backbone is **ModernBERT-Large**, the same
architecture family as our Granite embedder, which we already drive onto the ANE. Can it be ported?

**Answer: yes — full ANE residency, and the calibration survives.**

**Run:** 2026-09-22 · macOS 27.0 · base M4 · `coreai-build` 3600.83.1 · `coreai-torch` 0.4.2

---

## Result

| | |
| --- | --- |
| AOT compile (ANE, h16g) | **exit 0**, 5 s |
| ANE residency | **3 regions (v1), 0 GPU, 0 CPU — full.** The first build was 31 regions; the fp32-ism ladder below took it to 3 |
| Argmax vs HF fp32 | **correct on every case** |
| Probability error | **≤ 0.33 points** (worst of 5 cases) |
| Latency | **24 ms/decision** ANE (v1, 3 regions) · 39 ms GPU — *the ANE is faster* |
| Later (EXP-018) | On JevBench's suite the same bundle measures **105 ms/decision, Intelligence 36.2** — matching the CPU row exactly. Von's NLI mapping makes one pass *per option*; Laya's native head scores all options in one, which is why Laya is 29× on the ANE and Von is ~1×. See `von-ane-crash-research.md` §7–§9 |

```
case            HF fp32 (E/N/C)          ANE fp16                  max|dp|
blocking        0.023 0.450 0.526        0.024 0.451 0.525          0.0014
unrelated       0.000 0.842 0.157        0.000 0.842 0.158          0.0009
contradiction   0.000 0.004 0.996        0.000 0.005 0.995          0.0004
entailment      0.037 0.954 0.009        0.038 0.953 0.009          0.0006
borderline      0.000 0.109 0.891        0.000 0.113 0.887          0.0033
```

**Why this matters for a decision model:** Von is *calibrated* — post-trained with Brier loss and a
fitted temperature (T = 1.1692), so `P = 0.94` is meant to mean 94%. fp16 preserving that to within
**0.33 points** is the property that makes it usable as a threshold primitive. A logit-space check
would have called this a failure; it is the wrong metric.

## What the port required

Reused the zoo's ModernBERT re-authoring (`conversion/granite_embedding/_granite_model.py`) as the
template, which already solves the traps this session hit the hard way:

- **RoPE cos/sin as precomputed buffers**, not gathered in-graph — the F-34 segfault
- **layer 0 has no attention norm** — HF omits it; Von's weights have 27 `attn_norm`, not 28
- **fused `Wqkv`**, and fused `Wi` → `chunk(2)`
- explicit matmul + fp32 softmax, **no fused SDPA**

Then four things taken from Von's own config and weights rather than assumed:

| difference | source |
| --- | --- |
| `hidden_activation: gelu` (Granite is silu) | config |
| `classifier_pooling: mean` (Granite is CLS) | config |
| `norm_bias: false` — **no norm biases exist** in the checkpoint | safetensors |
| 3-way head `Linear(1024,3)`, **padded to 32** for 64-byte alignment | config + the alignment rule |

**Graph:** `input_ids [1,256] → 28 layers → masked mean pool → dense(1024→1024) → GELU →
LayerNorm → classifier(1024→3) → pad to 32`.

**Torch gate before exporting:** worst `|dlogit|` vs HF fp32 = **8.58e-06** — so the re-authoring is
exact and the only error introduced afterwards is the fp16 cast.

## The v0→v3 ladder: 31 regions → 3, and 74 ms → 24 ms

The first build was **segmented at 31 regions** and slower than the GPU. That is the *same* symptom
Granite had, and the *same* fix applies — `bench/granite_ane_variants.py`'s fp32-ism ladder, which
took Granite from 13 regions to 1. I had copied those fp32-isms out of the template without noticing.

| variant | change | ANE regions | latency | worst Δp |
| --- | --- | ---: | ---: | ---: |
| **v0** | as-is (fp32 softmax, float-literal scale) | **31** | **74 ms** | 0.0033 |
| **v1** | **softmax in the graph dtype** | **3** | **24 ms** | **0.0027** |
| v2 | + rope/scale as f16 buffers | 3 | — | (torch gate 1.19e-03) |
| v3 | + dtype-matched mask/pool literals | 3 | — | (torch gate 1.19e-03) |

**The fp32 softmax alone was worth 28 regions.** v2/v3 buy no further residency and *cost* accuracy
(the torch gate degrades from 8.58e-06 to 1.19e-03), so **v1 is the sweet spot** — 3 regions at
unchanged precision.

**And that inverts the ANE/GPU result:**

| | latency |
| --- | ---: |
| v0 on the ANE (31 regions) | 74 ms |
| **v1 on the ANE (3 regions)** | **24 ms** |
| GPU delegate | 39 ms |

**24 ms also matches Von's own claimed ~18 ms** — which was measured on MPS, not the ANE.

This is the second time this session that a *segmented* ANE graph looked like an ANE limitation when
it was an authoring problem, and the second time the fix was the same: **remove the fp32 ops**.

## The latency caveat — 31 regions is 31 submissions

**54 ms on the ANE vs 39 ms on the GPU.** The zoo's own measurement explains it: *"25 regions are 25
submissions"* — ~1.1 ms per boundary. At 31 regions that is roughly **30 ms of submission overhead**,
which is most of the gap. A single-region build (as our reranker achieves) should be substantially
faster; the region count is the lever, not the arithmetic.

## Benchmarked on Von's own comparison suite (authored144)

The 5 hand-written cases above were only a smoke test. This runs **Von's own benchmark** —
`benchmarks/data/authored144.jsonl`, the 144-row suite their `run_comparison.py` profiles — through
both the HF reference and our ANE build, using **their scoring logic copied verbatim** from
`berta_backend.py::evaluate_choice` (per-option hypothesis `"{instructions} {description}"`, premise =
state, entailment logit, argmax over options).

| backend | raw acc | balanced acc | median latency |
| --- | ---: | ---: | ---: |
| HF (fp32, CPU) | 70.8% | 70.3% | 201 ms |
| **OURS (ANE, fp16, v1)** | **70.8%** | **70.3%** | **74 ms** |

**Port fidelity: 144/144 predictions identical. Balanced-accuracy delta: +0.00 points.**
**The ANE is 2.7× faster than the CPU reference.**

The 70.3% is also a second, independent check that we have the **correct checkpoint**: issue #5
records that a bad revision lost its head and `transformers` silently random-initialised one. A
random head could not score 70.3% on a real suite.

### Where that sits

| model | size | balanced acc | latency | hardware |
| --- | ---: | ---: | ---: | --- |
| OpenJev (Qwen3.5-4B) | 3.01 GB | **81.3%** | ~48 ms | RTX 3090 |
| **Von (ours, ANE)** | **790 MB** | **70.3%** | **74 ms** | **ANE (M4)** |
| Von (HF reference) | 790 MB | 70.3% | 201 ms | CPU |

**We are 11 points behind OpenJev on accuracy** — but OpenJev is a 4B model on a 3090, and we are a
395M model on the Neural Engine. That is the trade the port is making, and it is the honest framing
rather than an accuracy win.

## The closest prior art, found by checking upstream

**`aac6fef/laya-multilingual-coreml-ane`** — a *comparable decision model* (Laya, mmBERT-based)
**already ported to the ANE**, via **Core ML** rather than Core AI:

| | their Laya port | ours (Von) |
| --- | --- | --- |
| toolchain | Core ML (macOS 15+) | Core AI (macOS 27) |
| latency | **4.98 ms P50 / 5.31 ms P95** (M3 Max) | 74 ms |
| **token budget** | **96** | **256** |
| option slots | 32 | 3-way head |
| **energy** | **2.78× better than MLX FP16** | **not measured** |
| fidelity | 59/59 fixtures, 100 repeated calls | 144/144 rows |

**They are far faster than us** — though at **96 tokens against our 256**, so much of that is budget
rather than efficiency. Two things their README does that ours should:

- *"Inputs longer than 96 tokens **raise an error** instead of being silently shortened to fit."*
- *"Port fidelity on this regression suite **does not establish general task accuracy or preserved
  calibration** on arbitrary inputs."*

And they published a miss: *"The requested 10× improvement was not achieved."*

**The lesson from their row is that energy is the axis where the ANE actually wins** — 2.78× over
MLX — and it is the one number we still have not measured.

## Caveats

- **5 cases**, hand-written, not a benchmark. Von's own claim is 72.0% macro on the 49-task jabr v2
  suite; nothing here re-measures that.
- Latency is a median of 5 single calls, not a sustained run — no p95, no thermal control.
- One grid (S=256), one chip (M4/h16g).
- **Von is Apache-2.0 and not gated** — unlike EmbeddingGemma, no licence gate, no token.
- Energy not measured.

## Artifacts

- `bench/export_von_ane.py` — the re-authoring + torch gate
- `work/exports/von-ane/von-1.0_float16_s256_ane.aimodel` — the source graph
- `work/exports/von-ane/aot_h16g_ane/*.h16g.aimodelc` — **the ANE bundle (31 regions)**
- `models/von-1.0/` — the upstream weights

---

## Measurements (generated)

> Generated from `results/measurements.json` by `bench/results_table.py`. **Do not hand-edit** — regenerate.
> Rows appear only when another row is genuinely comparable; `benchmark+split+scope+tiers+metric+unit`
> must agree. See `results/CONSISTENCY-PLAN.md` for why.

| id | model | placement | dtype | seq_len | metric | value | unit | latency_ms | latency_unit | provenance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| von-ane-s256 | Von-1.0 (ModernBERT-large, 3-way NLI) | ANE | fp16 | 256 | Intelligence | 36.2 | chance-corrected, 0-100 | 105.0 | per decision (N option passes; NLI mapping) | ours |
| von-cpu-s256 | Von-1.0 (ModernBERT-large, 3-way NLI) | CPU | fp16 | 256 | Intelligence | 36.2 | chance-corrected, 0-100 | 98.0 | per decision (N option passes; NLI mapping) | ours |
| von-v0-ane-regions | Von-1.0 | ANE | fp16 (as-is: fp32 softmax, float-literal scale) | 256 | ANE regions | 31 | regions | — | — | ours |
| von-v0-ane-latency | Von-1.0 | ANE | fp16 (as-is: fp32 softmax, float-literal scale) | 256 | latency | 74 | ms | 74 | per decision (median of 5 single calls) | ours |
| von-v0-worst-dp | Von-1.0 | ANE | fp16 (as-is: fp32 softmax, float-literal scale) | 256 | worst \|dp\| | 0.0033 | absolute probability delta (0-1 scale) | — | — | ours |
| von-v1-ane-regions | Von-1.0 | ANE | fp16 (softmax in graph dtype) | 256 | ANE regions | 3 | regions | — | — | ours |
| von-v1-ane-latency | Von-1.0 | ANE | fp16 (softmax in graph dtype) | 256 | latency | 24 | ms | 24 | per decision (median of 5 single calls) | ours |
| von-v1-worst-dp | Von-1.0 | ANE | fp16 (softmax in graph dtype) | 256 | worst \|dp\| | 0.0027 | absolute probability delta (0-1 scale) | — | — | ours |
| von-v2-f16-buffers-ane-regions | Von-1.0 | ANE | fp16 (rope/scale as f16 buffers) | 256 | ANE regions | 3 | regions | — | — | ours |
| von-v2-f16-buffers-torch-gate | Von-1.0 | — | fp16 (rope/scale as f16 buffers) | 256 | torch gate worst \|dlogit\| | 0.00119 | absolute logit delta | — | — | ours |
| von-v3-f16-literals-ane-regions | Von-1.0 | ANE | fp16 (dtype-matched mask/pool literals) | 256 | ANE regions | 3 | regions | — | — | ours |
| von-v3-f16-literals-torch-gate | Von-1.0 | — | fp16 (dtype-matched mask/pool literals) | 256 | torch gate worst \|dlogit\| | 0.00119 | absolute logit delta | — | — | ours |
| von-v1-torch-gate | Von-1.0 | — | fp16 | 256 | torch gate worst \|dlogit\| vs HF fp32 | 8.58e-06 | absolute logit delta | — | — | ours |
| von-gpu-delegate-latency | Von-1.0 | GPU | fp16 | 256 | latency | 39 | ms | 39 | per decision (median of 5 single calls) | ours |
| von-aot-compile-time | Von-1.0 | — | — | 256 | AOT compile wall time | 5 | s | — | — | ours |
| von-max-prob-error | Von-1.0 | ANE | fp16 (v1) | 256 | max probability error vs HF fp32 | 0.33 | percentage points (probability, 0-100 scale) | — | — | ours |
| von-jevbench-intelligence | Von-1.0 | ANE | fp16 (v1) | 256 | Intelligence | 36.2 | chance-corrected 0-100 | 105 | per decision | ours |
| von-jevbench-latency | Von-1.0 | ANE | fp16 (v1) | 256 | latency | 105 | ms | 105 | per decision | ours |
| von-temperature | Von-1.0 | — | — | 256 | fitted temperature T | 1.1692 | dimensionless | — | — | ours |
| von-case-blocking-hf-e | Von-1.0 | — | fp32 | 256 | probability (E) | 0.023 | probability (0-1) | — | — | ours |
| von-case-blocking-hf-n | Von-1.0 | — | fp32 | 256 | probability (N) | 0.45 | probability (0-1) | — | — | ours |
| von-case-blocking-hf-c | Von-1.0 | — | fp32 | 256 | probability (C) | 0.526 | probability (0-1) | — | — | ours |
| von-case-blocking-ane-e | Von-1.0 | ANE | fp16 (v1) | 256 | probability (E) | 0.024 | probability (0-1) | — | — | ours |
| von-case-blocking-ane-n | Von-1.0 | ANE | fp16 (v1) | 256 | probability (N) | 0.451 | probability (0-1) | — | — | ours |
| von-case-blocking-ane-c | Von-1.0 | ANE | fp16 (v1) | 256 | probability (C) | 0.525 | probability (0-1) | — | — | ours |
| von-case-blocking-max-dp | Von-1.0 | ANE | fp16 (v1) | 256 | max \|dp\| | 0.0014 | absolute probability delta (0-1 scale) | — | — | ours |
| von-case-unrelated-hf-e | Von-1.0 | — | fp32 | 256 | probability (E) | 0.0 | probability (0-1) | — | — | ours |
| von-case-unrelated-hf-n | Von-1.0 | — | fp32 | 256 | probability (N) | 0.842 | probability (0-1) | — | — | ours |
| von-case-unrelated-hf-c | Von-1.0 | — | fp32 | 256 | probability (C) | 0.157 | probability (0-1) | — | — | ours |
| von-case-unrelated-ane-e | Von-1.0 | ANE | fp16 (v1) | 256 | probability (E) | 0.0 | probability (0-1) | — | — | ours |
| von-case-unrelated-ane-n | Von-1.0 | ANE | fp16 (v1) | 256 | probability (N) | 0.842 | probability (0-1) | — | — | ours |
| von-case-unrelated-ane-c | Von-1.0 | ANE | fp16 (v1) | 256 | probability (C) | 0.158 | probability (0-1) | — | — | ours |
| von-case-unrelated-max-dp | Von-1.0 | ANE | fp16 (v1) | 256 | max \|dp\| | 0.0009 | absolute probability delta (0-1 scale) | — | — | ours |
| von-case-contradiction-hf-e | Von-1.0 | — | fp32 | 256 | probability (E) | 0.0 | probability (0-1) | — | — | ours |
| von-case-contradiction-hf-n | Von-1.0 | — | fp32 | 256 | probability (N) | 0.004 | probability (0-1) | — | — | ours |
| von-case-contradiction-hf-c | Von-1.0 | — | fp32 | 256 | probability (C) | 0.996 | probability (0-1) | — | — | ours |
| von-case-contradiction-ane-e | Von-1.0 | ANE | fp16 (v1) | 256 | probability (E) | 0.0 | probability (0-1) | — | — | ours |
| von-case-contradiction-ane-n | Von-1.0 | ANE | fp16 (v1) | 256 | probability (N) | 0.005 | probability (0-1) | — | — | ours |
| von-case-contradiction-ane-c | Von-1.0 | ANE | fp16 (v1) | 256 | probability (C) | 0.995 | probability (0-1) | — | — | ours |
| von-case-contradiction-max-dp | Von-1.0 | ANE | fp16 (v1) | 256 | max \|dp\| | 0.0004 | absolute probability delta (0-1 scale) | — | — | ours |
| von-case-entailment-hf-e | Von-1.0 | — | fp32 | 256 | probability (E) | 0.037 | probability (0-1) | — | — | ours |
| von-case-entailment-hf-n | Von-1.0 | — | fp32 | 256 | probability (N) | 0.954 | probability (0-1) | — | — | ours |
| von-case-entailment-hf-c | Von-1.0 | — | fp32 | 256 | probability (C) | 0.009 | probability (0-1) | — | — | ours |
| von-case-entailment-ane-e | Von-1.0 | ANE | fp16 (v1) | 256 | probability (E) | 0.038 | probability (0-1) | — | — | ours |
| von-case-entailment-ane-n | Von-1.0 | ANE | fp16 (v1) | 256 | probability (N) | 0.953 | probability (0-1) | — | — | ours |
| von-case-entailment-ane-c | Von-1.0 | ANE | fp16 (v1) | 256 | probability (C) | 0.009 | probability (0-1) | — | — | ours |
| von-case-entailment-max-dp | Von-1.0 | ANE | fp16 (v1) | 256 | max \|dp\| | 0.0006 | absolute probability delta (0-1 scale) | — | — | ours |
| von-case-borderline-hf-e | Von-1.0 | — | fp32 | 256 | probability (E) | 0.0 | probability (0-1) | — | — | ours |
| von-case-borderline-hf-n | Von-1.0 | — | fp32 | 256 | probability (N) | 0.109 | probability (0-1) | — | — | ours |
| von-case-borderline-hf-c | Von-1.0 | — | fp32 | 256 | probability (C) | 0.891 | probability (0-1) | — | — | ours |
| von-case-borderline-ane-e | Von-1.0 | ANE | fp16 (v1) | 256 | probability (E) | 0.0 | probability (0-1) | — | — | ours |
| von-case-borderline-ane-n | Von-1.0 | ANE | fp16 (v1) | 256 | probability (N) | 0.113 | probability (0-1) | — | — | ours |
| von-case-borderline-ane-c | Von-1.0 | ANE | fp16 (v1) | 256 | probability (C) | 0.887 | probability (0-1) | — | — | ours |
| von-case-borderline-max-dp | Von-1.0 | ANE | fp16 (v1) | 256 | max \|dp\| | 0.0033 | absolute probability delta (0-1 scale) | — | — | ours |
| von-a144-hf-raw-acc | Von-1.0 | CPU | fp32 | 256 | raw accuracy | 70.8 | % (raw accuracy over 144 rows) | — | — | ours |
| von-a144-hf-balanced-acc | Von-1.0 | CPU | fp32 | 256 | balanced accuracy | 70.3 | % (balanced accuracy) | — | — | ours |
| von-a144-hf-median-latency | Von-1.0 | CPU | fp32 | 256 | median latency | 201 | ms | 201 | per decision (median over 144 rows) | ours |
| von-a144-ane-raw-acc | Von-1.0 | ANE | fp16 (v1) | 256 | raw accuracy | 70.8 | % (raw accuracy over 144 rows) | — | — | ours |
| von-a144-ane-balanced-acc | Von-1.0 | ANE | fp16 (v1) | 256 | balanced accuracy | 70.3 | % (balanced accuracy) | — | — | ours |
| von-a144-ane-median-latency | Von-1.0 | ANE | fp16 (v1) | 256 | median latency | 74 | ms | 74 | per decision (median over 144 rows) | ours |
| von-a144-identical-predictions | Von-1.0 | ANE | fp16 (v1) | 256 | predictions identical to HF reference | 144 | rows (of 144) | — | — | ours |
| von-a144-balanced-acc-delta | Von-1.0 | ANE | fp16 (v1) | 256 | balanced accuracy delta | 0.0 | absolute delta over HF fp32 reference (points) | — | — | ours |
| von-a144-speedup-vs-cpu | Von-1.0 | ANE | fp16 (v1) | 256 | speedup vs CPU reference | 2.7 | × (speedup) | — | — | ours |
| von-size-ane | Von-1.0 | ANE | fp16 (v1) | 256 | model size | 790 | MB | — | — | ours |
| von-size-hf | Von-1.0 | CPU | fp32 | 256 | model size | 790 | MB | — | — | ours |
| von-openjev-acc-gap | Von-1.0 | ANE | fp16 (v1) | 256 | balanced accuracy gap vs OpenJev | 11 | absolute delta over OpenJev (percentage points) | — | — | ours |
| von-token-budget | Von-1.0 | ANE | fp16 (v1) | 256 | token budget | 256 | tokens | — | — | ours |
| von-vendor-latency-mps | Von-1.0 | MPS | — | — | latency | 18 | ms | 18 | per decision | vendor (Von, wfzyx/von) |
| von-vendor-jabr-v2-macro | Von-1.0 | — | — | — | macro accuracy | 72.0 | % (macro accuracy) | — | — | vendor (Von, wfzyx/von) |
| von-easy | Von-1.0 | CPU | — | — | easy tier accuracy | 100.0 | % accuracy | — | — | ours |
| von-standard | Von-1.0 | CPU | — | — | standard tier accuracy | 61.1 | % accuracy | — | — | ours |
| von-hard | Von-1.0 | CPU | — | — | hard tier accuracy | 30.6 | % accuracy | — | — | ours |
| von-intel | Von-1.0 | CPU | — | — | Intelligence | 36.2 | chance-corrected 0-100 | — | — | ours |
| von-p50 | Von-1.0 | CPU | — | — | raw p50 latency | 98.3 | ms | 98.3 | per decision (one forward pass per option - N passes) | ours |
| von-hard-vs-chance | Von-1.0 | CPU | — | — | hard tier accuracy vs chance baseline | 30.6 | % accuracy (chance baseline 33.6%) | — | — | ours |
| von-table-laya-ref-easy | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | easy tier accuracy (Von-table reference column) | 95.8 | % accuracy | — | — | ours |
| von-table-laya-ref-standard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | standard tier accuracy (Von-table reference column) | 70.8 | % accuracy | — | — | ours |
| von-table-laya-ref-hard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | hard tier accuracy (Von-table reference column) | 35.1 | % accuracy | — | — | ours |
| von-table-laya-ref-intel | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | Intelligence (Von-table reference column) | 41.5 | chance-corrected 0-100 | — | — | ours |
| von-table-laya-ref-p50 | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | raw p50 latency (Von-table reference column) | 68.1 | ms | 68.1 | per decision (all options scored in one pass) | ours |
| von-bundle-cpu-exit | Von-1.0 | CPU | fp16 | 256 | process exit code (AIModel.load + compute) | 0 | exit code | — | — | ours |
| von-bundle-gpu-exit | Von-1.0 | GPU | fp16 | 256 | process exit code (AIModel.load + compute) | 139 | exit code | — | — | ours |
| von-bundle-ane-exit | Von-1.0 | ANE | fp16 | 256 | process exit code (AIModel.load + compute) | 139 | exit code | — | — | ours |
| von-ane-p50-exp016 | Von-1.0 | ANE | — | 256 | raw p50 latency (as recorded in EXP-016) | 74 | ms | 74 | per decision (one forward pass per option - N passes) | ours |
