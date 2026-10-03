# EXP-013 — re-authoring the reranker for the Neural Engine

**Question.** F-32 found the published reranker returns a constant `0.5` on the ANE, and traced it
to the bundle being a stock **macOS/GPU** export that was never authored for the ANE. Can it be
re-authored into Apple's ANE dialect — the same treatment that took our embedder from off-ANE to 14
ANE regions?

**Answer: yes.** The re-authored graph compiles to a **single full-ANE region** and **passes the
gate on the ANE delegate**.

**Run:** 2026-09-21 · macOS 27.0 · base M4 (16 GB) · `coreai-build` 3600.83.1 · MetalToolchain v27.1.266.1

---

## Result

| | |
| --- | --- |
| AOT compile (ANE, h16g) | **exit 0**, 17 s |
| ANE residency | **1 region, `main_..._0_ANE_region_0_0` — ANE only, no GPU/CPU segments** |
| Gate on the **ANE delegate** | **PASS** — worst \|Δ\| **6.11e-04** vs the published official scores |
| Ranking on the ANE | **all 3 groups correct** |
| ANE vs GPU numerics | **identical** (6.11e-04 both) |

```
pair              official         ANE         GPU   |d| ANE
rel_capital       0.993775    0.993164    0.993164  6.11e-04
rel_beesting      0.981483    0.981934    0.981934  4.51e-04
rel_fuji_ja       0.999777    1.000000    1.000000  2.23e-04
irr_capital       0.000009    0.000009    0.000009  5.08e-08
irr_beesting      0.000036    0.000037    0.000037  1.32e-06
irr_fuji_ja       0.000006    0.000006    0.000006  2.77e-08
```

**The constant `0.5` is gone.** The ANE now returns the real numbers, and they match the GPU.

## The fix: RoPE out of the graph

The graph segfaulted `coreai-build` until one thing changed. The zoo's own authoring rules name it:

> `knowledge/compute-units-and-authoring.md:39` — *"**RoPE as input**: precompute cos/sin outside
> the graph, pass as 4D `(1, head_dim, 1, S)` (**in-graph `gather_nd` makes rank-3 → ANE rejects**)."*

Our graph called `RoPECache.gather_cos_sin(position_ids)` — **an in-graph gather**. Hoisting it to
the host (cos/sin arrive as graph inputs, shape `(1, S, 128)`) turned:

```
1 layer, RoPE gathered in-graph   →  coreai-build exit 139 (SIGSEGV)
1 layer, RoPE passed as an input  →  coreai-build exit 0
```

and the full 28-layer model then compiled to a single ANE region.

This also explains the **`0.5`**: the published bundle compiles to **0 ANE regions** (silent GPU
fallback), so on the ANE delegate it produced a constant. Two independent symptoms, one root cause —
the graph was not ANE-shaped.

## What was re-authored

Reusing **Apple's own verified ANE Qwen3** (`coreai_models.models.ios.qwen3`) rather than
hand-rolling 28 layers, plus five changes for the cross-encoder shape:

| # | change | why |
| --- | --- | --- |
| 1 | **`nn.Linear` → 1×1 `Conv2d`**, weight `[O,I] → [O,I,1,1]`; activations `(B,S,1,D)` transposing to BC1S `(B,C,1,S)` per projection | *"Linear falls back off-ANE"* |
| 2 | **`[x,-x]` LayerNorm RMSNorm trick**, 113 norms | composite RMSNorm overflows in fp16 — see below |
| 3 | **RoPE cos/sin as graph inputs**, no in-graph gather | the segfault fix above |
| 4 | **last-token one-hot as a graph input** | removes an in-graph concat against a constant (the zoo's documented constant-mask segfault pattern) |
| 5 | **head projects to 2 rows, not 151669**; output padded to 32 | removes a non-power-of-2 width; the alignment rule wants ≥ 32 fp16 (64 B) on the last axis, and `[B,2]` is 4 B |

Plus: causal mask `-40000.0` not `-inf`, passed as an input; fp16 throughout.

## The `[x,-x]` fix was a real bug, not a precaution

The first fp16 build scored **0.877 where HF scores 0.994**, while the *same graph in fp32* matched
to `1.19e-07`. Apple's rules name the cause:

> *"**RMSNorm trap**: composite RMSNorm computes `mean(x²)` in fp16 → **overflows** large
> activations. Use the `[x,-x]` LayerNorm trick ... the ANE runs LayerNorm with an fp32-accumulating
> hardware kernel."*

`LayerNorm([x,-x])` has zero mean by construction, so it equals RMSNorm. After swapping 113 norms:
worst |Δ| **4.51e-04** — a ~1000× improvement, and the difference between a correct graph and a
plausible-looking wrong one. Recipe: the ANEMLL article *"RMS Norm on the Apple Neural Engine: A
Simple Hack"* (2025-09-16) and the zoo's `gemma4_ane_chunks._Fp32RMSNorm`.

## End-to-end: the ANE reranker in the real pipeline

The 6-pair gate is not a retrieval benchmark, so the whole SciFact pipeline (EXP-011's chunk index
+ EXP-012's harness) was re-run with the ANE server swapped in for the GPU one — same corpus, same
300 queries, same K=20 shortlist:

| reranker | ndcg@10 | recall@10 | ceiling | time |
| --- | ---: | ---: | ---: | ---: |
| GPU (EXP-012) | 0.75784 | 0.85900 | 0.8740 | 1021 s (3.40 s/query) |
| **ANE** | **0.75860** | **0.85900** | 0.8740 | **538 s (1.79 s/query)** |

**`recall@10` is identical to five decimals and `ndcg@10` is within 0.0008.** The small ndcg gap is
the 6e-04 score difference flipping close rankings — the same effect that made the per-query
running averages diverge slightly from the GPU run after ~query 70. Not a quality difference.

## Timing — and a discrepancy I could not resolve

| measurement | ANE | GPU |
| --- | ---: | ---: |
| direct, single pair, in-process (gate) | 88 ms | 87 ms |
| through the pipeline (server) | **89 ms** (1.79 s/query) | **170 ms** (3.40 s/query) |

The ANE server matches its own direct measurement (89 vs 88 ms). **The GPU *server* is ~2× slower
than the GPU direct measurement (170 vs 87 ms)** — so the pipeline gap looks like server overhead
on the GPU path (HTTP/threading or per-call synchronisation), not an accelerator difference.

**The honest statement is: the ANE is at least as fast, and in this pipeline it finished in half
the wall-clock.** I would not claim the ANE computes faster per pair on this evidence — the direct
measurements say they are equal, and the difference appears in the server layer. Resolving that
needs profiling the GPU server, which was not done.

The stronger case for the ANE remains **energy**, not speed: EXP-003 measured 5.6× less energy per
embedding on the ANE, and the zoo's sustained-load data shows the ANE holding ~67% of burst where
the GPU throttles to ~38%. Neither was re-measured here.

## Original timing note (gate only)

| | load | median |
| --- | ---: | ---: |
| ANE | 33.45 s | 88 ms/pair |
| GPU | 5.01 s | 87 ms/pair |

**Effectively identical latency**, and the ANE's cold load is ~7× slower. The case for the ANE is
**energy**, not speed: EXP-003 measured the embedder at **5.6× less energy per embedding** on the
ANE, and the zoo's sustained-load data shows the ANE holding ~67% of its burst throughput where the
GPU throttles to ~38%. Neither was re-measured here — `powermetrics`' `ane_power` is documented in
the zoo as unreliable (two runs of one workload reported ~1.9 W and ~0 mW), so an energy claim needs
a better instrument than we had.

## How the bisection went wrong, and what fixed it

Worth recording, because two wrong conclusions were reached confidently on the way:

1. **"Not RoPE."** Apple's `qwen3.py` does `from ...rope import apply_rope`, so it holds **its own
   reference**; patching `rope.apply_rope` was a **silent no-op**. Every "no-rope" run was really a
   with-rope run. Patching the name in the *consumer's* namespace flipped the result immediately.
   **A no-op stub looks exactly like a negative result.**
2. **"Wrong route to the ANE."** Reading upstream issue #55 suggested the dynamic macOS path was a
   dead end for the ANE. But our own PR #36 already recorded the counter-evidence: the embedder
   reaches the ANE this way (13 → 1 region) and *"placement is baked at compile time"*. **The route
   was fine; the graph was not.**

The search that actually cracked it was reading the zoo's **authoring rules**, not the bug trackers.
The rule for the failing op was already written down.

## Caveats

- The gate is the 6 pairs in `reference.json`, not a retrieval benchmark. A full MTEBNE-vs-GPU A/B
  is the natural next measurement.
- ANE load is 33 s cold (specialization); warm loads are cached by the OS.
- Energy was **not** measured (see above).
- One chip (M4, h16g), one grid (S=512).

## Artifacts

- `bench/export_reranker_ane.py` — the re-authoring
- `bench/gate_reranker_ane.py` — the ANE-delegate gate + ANE/GPU timing
- `bench/minimal_repro_ane_crash.py`, `bench/repro_apple_attention.py` — the bisection
- `work/exports/reranker-ane/qwen3-reranker-0.6b_float16_s512_ane.aimodel` — the source graph
- `work/exports/reranker-ane/aot_h16g_ane/*.h16g.aimodelc` — **the ANE bundle (1.1 GB, 1 region)**

---

## Measurements (generated)

> Generated from `results/measurements.json` by `bench/results_table.py`. **Do not hand-edit** — regenerate.
> Rows appear only when another row is genuinely comparable; `benchmark+split+scope+tiers+metric+unit`
> must agree. See `results/CONSISTENCY-PLAN.md` for why.

| id | model | placement | dtype | seq_len | metric | value | unit | latency_ms | latency_unit | provenance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| reranker-ane-s512 | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | ndcg@10 delta | 0.0786 | absolute delta over retriever order | — | — | ours |
| aot-compile-ane-h16g | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | AOT compile time | 17 | s | — | — | ours |
| ane-residency-regions | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | ANE region count | 1 | regions | — | — | ours |
| gate-worst-delta-ane | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | worst absolute delta vs published official scores | 0.000611 | absolute score delta (0-1 scale) | — | — | ours |
| gate-groups-correct-ane | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | groups ranked correctly | 3 | groups correct (of 3) | — | — | ours |
| gate-worst-delta-ane-equals-gpu | Qwen3-Reranker-0.6B | ANE, GPU | fp16 | 512 | worst absolute delta vs official (ANE and GPU, reported identical) | 0.000611 | absolute score delta (0-1 scale) | — | — | ours |
| gate-rel_capital-ane | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | reranker score, pair rel_capital | 0.993164 | score (0-1) | — | — | ours |
| gate-rel_capital-gpu | Qwen3-Reranker-0.6B | GPU | — | 512 | reranker score, pair rel_capital | 0.993164 | score (0-1) | — | — | ours |
| gate-rel_capital-absdelta-ane | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | absolute delta vs official, pair rel_capital (ANE) | 0.000611 | absolute score delta over official | — | — | ours |
| gate-rel_beesting-ane | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | reranker score, pair rel_beesting | 0.981934 | score (0-1) | — | — | ours |
| gate-rel_beesting-gpu | Qwen3-Reranker-0.6B | GPU | — | 512 | reranker score, pair rel_beesting | 0.981934 | score (0-1) | — | — | ours |
| gate-rel_beesting-absdelta-ane | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | absolute delta vs official, pair rel_beesting (ANE) | 0.000451 | absolute score delta over official | — | — | ours |
| gate-rel_fuji_ja-ane | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | reranker score, pair rel_fuji_ja | 1.0 | score (0-1) | — | — | ours |
| gate-rel_fuji_ja-gpu | Qwen3-Reranker-0.6B | GPU | — | 512 | reranker score, pair rel_fuji_ja | 1.0 | score (0-1) | — | — | ours |
| gate-rel_fuji_ja-absdelta-ane | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | absolute delta vs official, pair rel_fuji_ja (ANE) | 0.000223 | absolute score delta over official | — | — | ours |
| gate-irr_capital-ane | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | reranker score, pair irr_capital | 9e-06 | score (0-1) | — | — | ours |
| gate-irr_capital-gpu | Qwen3-Reranker-0.6B | GPU | — | 512 | reranker score, pair irr_capital | 9e-06 | score (0-1) | — | — | ours |
| gate-irr_capital-absdelta-ane | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | absolute delta vs official, pair irr_capital (ANE) | 5.08e-08 | absolute score delta over official | — | — | ours |
| gate-irr_beesting-ane | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | reranker score, pair irr_beesting | 3.7e-05 | score (0-1) | — | — | ours |
| gate-irr_beesting-gpu | Qwen3-Reranker-0.6B | GPU | — | 512 | reranker score, pair irr_beesting | 3.7e-05 | score (0-1) | — | — | ours |
| gate-irr_beesting-absdelta-ane | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | absolute delta vs official, pair irr_beesting (ANE) | 1.32e-06 | absolute score delta over official | — | — | ours |
| gate-irr_fuji_ja-ane | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | reranker score, pair irr_fuji_ja | 6e-06 | score (0-1) | — | — | ours |
| gate-irr_fuji_ja-gpu | Qwen3-Reranker-0.6B | GPU | — | 512 | reranker score, pair irr_fuji_ja | 6e-06 | score (0-1) | — | — | ours |
| gate-irr_fuji_ja-absdelta-ane | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | absolute delta vs official, pair irr_fuji_ja (ANE) | 2.77e-08 | absolute score delta over official | — | — | ours |
| bisect-1layer-rope-ingraph-exit | Qwen3-Reranker-0.6B | ANE | — | 512 | coreai-build exit status (1 layer, RoPE gathered in-graph) | 139 | process exit code | — | — | ours |
| bisect-1layer-rope-input-exit | Qwen3-Reranker-0.6B | ANE | — | 512 | coreai-build exit status (1 layer, RoPE passed as graph input) | 0 | process exit code | — | — | ours |
| timing-direct-ane | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | latency, direct in-process single pair | 88 | ms | 88 | per pair (direct, in-process gate) | ours |
| timing-direct-gpu | Qwen3-Reranker-0.6B | GPU | — | 512 | latency, direct in-process single pair | 87 | ms | 87 | per pair (direct, in-process gate) | ours |
| timing-pipeline-ane-per-pair | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | latency, single pair through pipeline server | 89 | ms | 89 | per pair (through pipeline server) | ours |
| timing-pipeline-ane-per-query | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | latency, pipeline wall-clock per query | 1.79 | s/query | — | — | ours |
| timing-pipeline-gpu-per-pair | Qwen3-Reranker-0.6B | GPU | — | 512 | latency, single pair through pipeline server | 170 | ms | 170 | per pair (through pipeline server) | ours |
| timing-pipeline-gpu-per-query | Qwen3-Reranker-0.6B | GPU | — | 512 | latency, pipeline wall-clock per query | 3.4 | s/query | — | — | ours |
| gate-load-ane | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | model load time (cold) | 33.45 | s | — | — | ours |
| gate-load-gpu | Qwen3-Reranker-0.6B | GPU | — | 512 | model load time (cold) | 5.01 | s | — | — | ours |
| gate-median-ane | Qwen3-Reranker-0.6B | ANE | fp16 | 512 | median latency | 88 | ms | 88 | per pair (median, gate) | ours |
| gate-median-gpu | Qwen3-Reranker-0.6B | GPU | — | 512 | median latency | 87 | ms | 87 | per pair (median, gate) | ours |
| ane-bundle-size | Qwen3-Reranker-0.6B (ANE bundle) | ANE | fp16 | — | ANE compiled bundle size | 1.1 | GB | — | — | ours |
