# EXP-017 — Laya-multilingual on the Neural Engine: the closest prior art, reproduced on Core AI

**Question.** `aac6fef/laya-multilingual-coreml-ane` is the closest published prior art to the Von
port (EXP-016): a *comparable decision model* (Laya, mmBERT-based) already on the ANE — but via
**Core ML**, not Core AI, and at a **96-token budget**. Can the same model be driven onto the ANE on
the newer runtime, and how does it compare?

**Answer: yes — 2 ANE regions, confirmed ANE residency, and 1.12× faster per token than their
published number.**

**Run:** 2026-09-22 · macOS 27.0 · base M4 · `coreai-build` 3600.83.1 · `coreai-torch` 0.4.2

---

## Result

| | |
| --- | --- |
| AOT compile (ANE, h16g) | **exit 0**, 22/22 architecture variants |
| ANE residency | **2 regions** (Von v1 is 3; the first Von build was 31) |
| ANE actually ran | **102.3 GB moved, 2714 interrupts**, GPU at **9.8 mW** |
| Torch gate vs the reference forward | **4.77e-06 PASS** |
| Latency, S=256 | **11.83 ms P50 / 11.98 ms P95** |
| Fidelity sweep | **58/60 argmax**; both flips are near-ties (margin ≤ 0.004) |
| GPU power for the same graph | 9.8 mW (ANE) vs **255.9 mW** (forced to GPU) |

## Against the Core ML port

| | their Core ML port | ours (Core AI) |
| --- | --- | --- |
| latency | **4.98 ms P50 / 5.31 ms P95** | 11.83 ms P50 / 11.98 ms P95 |
| token budget | **96** | **256** |
| chip | M3 Max | **base M4** |
| **per-token** | **0.0519 ms** | **0.0462 ms** → **1.12× faster** |
| energy | 2.78× better than MLX FP16 | GPU 9.8 mW vs 255.9 mW (26×) |
| fidelity | 59/59 fixtures | 58/60 random sweep, flips are near-ties |

**The headline raw number goes their way (4.98 vs 11.83 ms) and that is mostly the budget** — 96
against 256 tokens, i.e. 2.67× the work. Normalised per token we are **1.12× faster, on a slower
chip**. Two honest caveats:

- their budget is 96, ours 256, so the comparison is only fair per token;
- their fixture suite (59/59) is a **published regression suite**, ours is 60 randomly generated
  cases. Theirs is the stronger evidence of fidelity.

## The three real bugs, and why each looked like something else

Each cost more than the last, and each was hidden by a silent-failure mechanism. All three were
found by *isolating one layer against HF with its exact input*, not by reading code.

| # | bug | cost | how it hid |
| --- | --- | ---: | --- |
| 1 | weight keys are `encoder.embeddings.*`, not `encoder.model.embeddings.*`; head keys keep the `layers.N.` prefix | 12.7 logits | `load_state_dict(strict=False)` **silently left all 24 head params at random init** |
| 2 | the head's FFN is **ReLU**, not GELU | 10.9 units | `nn.TransformerEncoderLayer`'s `activation` defaults to `relu`; Laya doesn't override it |
| 3 | **RoPE theta is 160000 for BOTH attention patterns**, not 10000 for sliding | **28.6 units** | the sliding layers were hardcoded to the wrong theta |

Bug 3 was the one that failed the gate: `abs(q_idx - kv_idx) <= 64` on 14 of 22 layers, plus a
theta 16× too small. Fixing all three took `worst |dlogit|` from **5.13e-01 → 4.77e-06**.

**A fourth trap, in the measurement rather than the model:** a "cumulative error of 147 at layer 21"
turned out to be my *test harness* comparing the pre-`final_norm` output of layer 21 against
`hidden_states[-1]`, which is **post-`final_norm`**. Every layer matched at ~1e-5 when fed HF's own
input. The lesson is the same one as EXP-016: **verify the harness before believing the failure.**

## What mmBERT needed that ModernBERT-Large (Von) did not

| difference | source |
| --- | --- |
| **`layer_types`: 8 full + 14 sliding attention** — each layer needs its own mask | config |
| sliding window **`abs(q-k) <= 64`**, ANDed with the padding mask | HF's `sliding_window_bidirectional_overlay` |
| `rope_theta: 160000` on **both** patterns | config |
| head is 2 `nn.TransformerEncoderLayer` with **`norm_first=True`**, 12 heads | `rl_agent_config.json` |
| **typed decision head**: `type_emb(qtype)` added after `final_norm`, then the encoder stack | `common.py` |
| option slots **32** (vs Von's 3-way) | `rl_agent_config.json` |

**The one change the ANE required:** Laya gathers the option-marker hidden states with
`torch.gather(h, 1, marker_pos)`. That was replaced by a **host-built one-hot selection matmul**,
`(1,K,S) @ (1,S,D) → (1,K,D)` — mathematically identical, and it keeps the graph static, which is
what lets it compile to 2 regions instead of segmenting.

## Energy — the axis where the ANE wins, and its limit

`tools/enginemon` (unprivileged IOReport) over the same workload:

```
ANE-specialised :  ANE activity  64.6 GB moved, 1774 interrupts
                   GPU Energy     9.8 mW      <- idle
GPU-specialised :  ANE activity  64.5 GB moved, 1738 interrupts
                   GPU Energy   255.9 mW      <- 26x
```

**Latency is identical (11.9 vs 11.6 ms); the GPU power is 26×.** That is the ANE's actual
advantage here: the same time, a fraction of the power.

**The limit, stated plainly:** the `Energy Model → ANE` channel is **frozen on M4** (it reads a
constant and never moves), so **total SoC energy is not measurable on this machine**. Only the GPU's
draw is. Our "energy" claim is therefore *GPU power avoided*, not a whole-chip joule count — and it
is not directly comparable to the Core ML port's 2.78×-vs-MLX figure, which was measured elsewhere.

## Caveats

- **Latency is a median of 30 calls**, no sustained run, no thermal control.
- **One grid (S=256), one chip (base M4 / h16g).** Their 4.98 ms is an M3 Max.
- **Fidelity is 60 random cases** plus 2 hand-written ones, not their 59-fixture suite. Both observed
  flips had a torch top1−top2 margin of **0.0038 and 0.0020** — the model was undecided — at
  `|dlogit|` of 5e-3 and 1.2e-2.
- **The 32 option slots are a fixed static shape.** Options beyond 32, or inputs beyond 256 tokens,
  are truncated — this is the failure mode their README explicitly avoids by *raising an error*, and
  **we do not do that. That is a real gap between the two ports.**
- `reference` in the export script is **our own re-derivation** from `common.py`, and the head
  `TransformerEncoder` is constructed with HF defaults (hence bug 2). It is not Laya's own forward.
- Energy: see above — GPU power only, ANE channel frozen.
- Laya is **Apache-2.0** and not gated.

## Artifacts

- `bench/export_laya_ane.py` — re-authoring, torch gate, Core AI export (`build_case` is shared)
- `bench/laya_ane_bench.py` — ANE runner: fidelity, sweep, latency, `--compute {neural_engine,gpu,cpu}`
- `work/exports/laya-ane/laya-multilingual_v1_float16_s256_ane.aimodel` — the source graph
- `work/exports/laya-ane/aot_h16g_ane/*.h16g.aimodelc` — **the ANE bundle (2 regions)**
- `work/laya-repo/` — the upstream repo, cloned to check for a published fixture suite
- `models/laya-multilingual/` — the upstream weights

---

## Measurements (generated)

> Generated from `results/measurements.json` by `bench/results_table.py`. **Do not hand-edit** — regenerate.
> Rows appear only when another row is genuinely comparable; `benchmark+split+scope+tiers+metric+unit`
> must agree. See `results/CONSISTENCY-PLAN.md` for why.

| id | model | placement | dtype | seq_len | metric | value | unit | latency_ms | latency_unit | provenance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| laya-ane-aot-exit-code | Laya-multilingual | ANE | fp16 | — | AOT compile exit code | 0 | exit code | — | — | ours |
| laya-ane-aot-variants | Laya-multilingual | ANE | fp16 | — | architecture variants compiled | 22 | variants (22/22 architecture variants) | — | — | ours |
| laya-ane-regions | Laya-multilingual | ANE | fp16 | 256 | ANE regions | 2 | regions | — | — | ours |
| laya-ane-memory-moved | Laya-multilingual | ANE | fp16 | 256 | ANE memory moved | 102.3 | GB | — | — | ours |
| laya-ane-interrupts | Laya-multilingual | ANE | fp16 | 256 | ANE interrupts | 2714 | interrupts | — | — | ours |
| laya-ane-gpu-power | Laya-multilingual | ANE | fp16 | 256 | GPU power (ANE-specialised run) | 9.8 | mW | — | — | ours |
| laya-ane-latency-p50-s256 | Laya-multilingual | ANE | fp16 | 256 | latency P50 | 11.83 | ms | 11.83 | per decision (one forward pass, all 32 option slots, S=256) | ours |
| laya-ane-latency-p95-s256 | Laya-multilingual | ANE | fp16 | 256 | latency P95 | 11.98 | ms | 11.98 | per decision (one forward pass, all 32 option slots, S=256) | ours |
| laya-ane-fidelity-argmax | Laya-multilingual | ANE | fp16 | 256 | argmax agreement with reference forward | 58 | matched cases (of 60) | — | — | ours |
| laya-ane-gpu-power-forced-gpu | Laya-multilingual | GPU | fp16 | 256 | GPU power (same graph forced to GPU) | 255.9 | mW | — | — | ours |
| laya-coreml-port-latency-p50 | Laya-multilingual (their Core ML port) | ANE | — | 96 | latency P50 | 4.98 | ms | 4.98 | per decision (one forward pass, S=96) | third-party (aac6fef/laya-multilingual-coreml-ane) |
| laya-coreml-port-latency-p95 | Laya-multilingual (their Core ML port) | ANE | — | 96 | latency P95 | 5.31 | ms | 5.31 | per decision (one forward pass, S=96) | third-party (aac6fef/laya-multilingual-coreml-ane) |
| laya-coreml-port-token-budget | Laya-multilingual (their Core ML port) | ANE | — | 96 | token budget | 96 | tokens | — | — | third-party (aac6fef/laya-multilingual-coreml-ane) |
| laya-ane-token-budget | Laya (aac6fef/laya-multilingual-coreml-ane) | ANE | — | 96 | token budget | 96 | tokens | — | — | third-party (aac6fef/laya-multilingual-coreml-ane README) |
| laya-coreml-port-per-token | Laya-multilingual (their Core ML port) | ANE | — | 96 | per-token latency | 0.0519 | ms per token | 0.0519 | per token | third-party (aac6fef/laya-multilingual-coreml-ane) |
| laya-ane-per-token | Laya-multilingual | ANE | fp16 | 256 | per-token latency | 0.0462 | ms per token | 0.0462 | per token | ours |
| laya-ane-per-token-speedup | Laya-multilingual | ANE | fp16 | 256 | per-token speedup vs Core ML port | 1.12 | x (ratio; ours on base M4 vs theirs on M3 Max) | — | — | ours |
| laya-coreml-port-energy-vs-mlx | Laya-multilingual (their Core ML port) | ANE | fp16 | 96 | energy vs MLX FP16 | 2.78 | x better than MLX FP16 (measured elsewhere) | — | — | third-party (aac6fef/laya-multilingual-coreml-ane) |
| laya-ane-gpu-power-ratio | Laya-multilingual | ANE | fp16 | 256 | GPU power ratio (forced GPU / ANE) | 26 | x | — | — | ours |
| laya-coreml-port-fidelity-fixtures | Laya-multilingual (their Core ML port) | ANE | — | 96 | fidelity | 59 | matching fixtures (of 59) | — | — | third-party (aac6fef/laya-multilingual-coreml-ane) |
| laya-bug1-cost | Laya-multilingual | ANE | fp16 | — | error from bug 1 (weight keys: encoder.embeddings.* vs encoder.model.embeddings.*) | 12.7 | logits | — | — | ours |
| laya-bug2-cost | Laya-multilingual | ANE | fp16 | — | error from bug 2 (head FFN activation ReLU instead of GELU) | 10.9 | units | — | — | ours |
| laya-bug3-cost | Laya-multilingual | ANE | fp16 | — | error from bug 3 (RoPE theta 160000 for both attention patterns, not 10000 for sliding) | 28.6 | units | — | — | ours |
| laya-dlogit-before-fixes | Laya-multilingual | ANE | fp16 | — | worst abs(dlogit) vs reference forward before the three bug fixes | 0.513 | absolute logit delta | — | — | ours |
| laya-gate-dlogit-after-fixes | Laya-multilingual | ANE | fp16 | — | worst abs(dlogit) vs reference forward (torch gate, PASS) | 4.77e-06 | absolute logit delta | — | — | ours |
| laya-enginemon-ane-moved | Laya-multilingual | ANE | fp16 | 256 | ANE activity: memory moved (ANE-specialised workload) | 64.6 | GB | — | — | ours |
| laya-enginemon-ane-interrupts | Laya-multilingual | ANE | fp16 | 256 | ANE activity: interrupts (ANE-specialised workload) | 1774 | interrupts | — | — | ours |
| laya-enginemon-gpu-moved | Laya-multilingual | GPU | fp16 | 256 | ANE activity: memory moved (GPU-specialised workload) | 64.5 | GB | — | — | ours |
| laya-enginemon-gpu-interrupts | Laya-multilingual | GPU | fp16 | 256 | ANE activity: interrupts (GPU-specialised workload) | 1738 | interrupts | — | — | ours |
