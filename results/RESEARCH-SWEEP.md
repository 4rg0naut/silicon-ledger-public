# Research sweep — what's moving in our field

**Date:** 2026-09-23 · sources are cited inline; nothing here is from memory.

---

## 1. The most important find: training on the ANE is real, and it's honest about itself

### `maderix/ANE` — **7,255 stars**, MIT
<https://github.com/maderix/ANE>

Backpropagation **directly on the ANE** via reverse-engineered `_ANEClient` / `_ANECompiler` /
`_ANEInMemoryModelDescriptor`. The stated thesis is ours:

> *"the barrier has always been **software support, not hardware capability**. The ANE is a remarkably
> capable piece of silicon that Apple restricts to inference-only use through CoreML."*

| Model | Params | ms/step |
| --- | ---: | ---: |
| Stories110M (12L, MHA) | 109M | **91 ms** |
| Qwen3-0.6B (28L, GQA) | 596M | **412 ms** |

| Precision | Peak TOPS (M4, H16G) |
| --- | ---: |
| FP16 | 18.6 |
| **INT8 W8A8** | **35.1** (1.88×) |

**The limitations are what matter, and the author states them plainly:**

- **Utilization is 5–9% of peak.**
- **Many element-wise ops still fall back to CPU.**
- *"This does **not** replace GPU training for anything beyond small research models today."*
- ANE **SDPA ignores `attn_mask`** — causal attention must be decomposed to CPU for the mask+softmax.
- **~119 ANE compile limit per process** (the compiler leaks) — worked around with an `exec()` restart.
- **fp16 gradient underflow** — needs global loss scaling (`256 × NLAYERS`).
- **Single-input constraint** — multi-input requests error, so inputs are packed into a spatial dim.

**And a disclaimer we have already lived through:** *"private, undocumented APIs… may change or break
with any macOS update."* That is the same fragility class as our Von crash.

### `ncdrone/rustane` — 182 stars, MIT
<https://github.com/ncdrone/rustane>

Rust-native, same idea, more recent. **"Trains transformer models at 3-5 W power draw, leaving the GPU
completely free. Training pipeline validated 48M → 5B params; forward confirmed to 30B. All on
M4 Max 128GB."**

**Note the machine: M4 Max 128GB** — the configuration our incoming M5 Max 128G matches.

**Read together, the verdict is clear: ANE training works and is immature.** 5–9% utilization with CPU
fallbacks means our current **MPS** training is the pragmatic path today, and the ANE remains the
**inference** win — which is where we measured it (26 ms/decision at 23 mW of GPU power).

---

## 2. Laya's author published the architecture in **March 2025**, and says so

<https://mgks.dev/rollups/2026-09-20-why-i-built-laya-open-source-system-1-for-real-production-speed/>

Ghazi Khan (ConvAI Innovations, `@NandhaKishorM` — the author of the checkpoint we ported) writes:

> *"In **March 2025**, I published an arXiv paper on non-autoregressive decision models trained with
> reinforcement learning… Then a well-funded frontier lab launched almost the exact same idea in
> September 2026 as if they invented it."*

He is claiming **Jev is a re-run of his 2025 work.** The HN thread is at
<https://news.ycombinator.com/item?id=49765348> — *"Jev was built using the same architecture Laya's
author proposed in March 2025."*

**This matters for us because it changes what "the field" is.** The category is ~18 months old, not
one month old, and the open version predates the famous one.

### And he independently confirms our calibration finding

> *"An English-only ModernBERT checkpoint with a 50,000-token BPE vocabulary completely fails on
> non-Latin alphabets. But here's the terrifying part: **its confidence never drops**. Accuracy on
> Devanagari might be 0%, yet the model outputs mean confidence of **0.885** anyway."*

**That is the same failure we measured** — our ECE was 0.2893 with the panel-doubt gap reproducing to
four decimals. He draws the production conclusion:

> *"**Confidence gating is useless.** You cannot use the model's own predictions to know when it's
> broken. **The routing decision must happen before the forward pass.**"*

His fix is a **Unicode-script Router across 22 alphabets** at <2% latency cost — and note it is the
opposite of the correctness head: he routes *before*, on the input; ours scores *after*, on the
output shape. **They are complementary.**

---

## 3. Other things worth having on the list

| what | URL | why |
| --- | --- | --- |
| **Laya official site** — *33 ms multilingual System 1* | <https://laya.convaiinnovations.com/> | the author's own hub; 6 arXiv papers |
| **`artificial-intelligence-works/laya-jev`** | <https://github.com/artificial-intelligence-works/laya-jev> | a direct Laya-vs-Jev comparison table |
| **`localai.computer`** Apple Silicon guide | <https://localai.computer/learn/apple-silicon-guide> | updated Sep 2026, practical |
| **arXiv 2608.22110** — *What actually runs: placement and decode speed on the ANE* | <https://arxiv.org/abs/2608.22110> | the measurement study closest to our work |
| **arXiv 2606.22283** — *ANE: Architecture, Programming, and Performance* | <https://arxiv.org/abs/2606.22283> | the reference paper on the hardware |
| **arXiv 2606.17090** — *ANEForge* | <https://arxiv.org/abs/2606.17090> | Python for direct ANE computation |
| **arXiv 2604.18788** — *MoE LLM inference with Apple Silicon NPUs* | <https://arxiv.org/abs/2604.18788> | sparse models + NPU |
| **Apple: MLX on M5 GPU Neural Accelerators** | <https://machinelearning.apple.com/research/exploring-llms-mlx-m5> | Apple's own; M5 GPU gains matrix units |
| **M5 Ultra / M6** — 2nm, quad-die | <https://me.pcmag.com/en/processors/37875/...> | arriving in Mac mini / Mac Studio |
| **`madewithjev.com`** | <https://madewithjev.com/builds/openjev-verdict-2> | the ecosystem showcase |
| **`BaseRT`** — LLM inference via native Metal | <https://arxiv.org/abs/2607.00501> | a different Metal-native route |

---

## 4. What this means for us, stated plainly

1. **ANE training is real but not ready** — 5–9% utilization, CPU fallbacks, a compile leak. **Keep
   training on MPS**, which is what our overnight run is doing.
2. **The ANE's win stays where we measured it: inference.** 26 ms/decision at 23 mW of GPU power.
3. **Our calibration finding is confirmed by the model's own author** — independently, with a different
   symptom (his over-confident-on-broken-inputs, ours over-confident-on-panel-doubt).
4. **His router + our correctness head are complementary** — route before the pass on the input, score
   after it on the output. Both are cheap; both target the axis JevBench doesn't cap.
5. **The category is older than the hype.** Laya's architecture was published March 2025. That is worth
   knowing before treating any of this as new.

## Still running

`ScanX`, `ScanReddit`, `ScanGitHub`, `ScanVideo` — their findings get appended here when they land.
---

# Part 2 — the four venue sweeps

**Venue access, stated plainly:** Reddit direct endpoints are **403/login-walled** (read via a redlib
mirror); **X is unreachable** for direct search (bot block; all Nitter mirrors dead) — X items below
are second-hand via `sotwe.com` and flagged as such. **HN and Bluesky are fully reachable without an
account.** Venues that produced nothing on-topic: `r/MachineLearning`, `r/MacStudio`,
`ml-explore/mlx` and `llama.cpp` (no ANE news in the window).

## The three most actionable finds

| finding | number | URL |
| --- | --- | --- |
| **M3 ANE DMA bandwidth erratum + workaround** | **10 → 24.3 tok/s** on Llama 3.2 1B (**2.4×**) | <https://eiln.github.io/posts/ane-dma.html> · HN 218 pts <https://news.ycombinator.com/item?id=49636479> |
| **Batched prefill on the ANE via private APIs** | **11.3× vs sequential**, **282× less GPU power** | <https://github.com/AtomGradient/hybird-batch-prefill-on-ane> |
| **`lfm2.5-vl-450M` fully on ANE** | prefill 85 ms · decode 57 tok/s · **1–2 W vs 8–15 W GPU** · residency 100%/92% | <https://github.com/shershah1024/lfm2.5-vl-ane> |

**The DMA erratum is the one to look at first.** A memory-alignment issue costing 2.4× — that is a
measurement of the same kind as our own 31→3 region ladder, and it may apply to our graphs.

**And `lfm2.5-vl-ane` re-teaches our own lesson:** it keeps **RMSNorm reductions in fp32**, because
*"true-fp16 reductions collapse bounding boxes."* That is the fp32-ism rule we learned the hard way.

## Apple's own tooling — and it moved today

| repo | stars | last push |
| --- | ---: | --- |
| **`apple/coreai-models`** | **2,136** | **2026-09-23 — today** |
| `apple/coreai-torch` | 156 | 2026-09-10 |
| `apple/coreai-optimization` | 136 | 2026-09-21 |

**`coreai-models` ships official agent "skills" encoding the ANE authoring rules** — BC1S layout, op
compatibility, KV-cache patterns, precision, MoE, and a **`common_issues.md`**. That is the upstream
we forked, and it is being actively pushed.

## The private-API ANE runtime cluster

| project | stars | note |
| --- | ---: | --- |
| **`johnmai-dev/ANE-LM`** | **143** | the upstream most others fork; **stale since 2026-03** |
| `thebasedcapital/ane-infer` | 28 | concrete RE result: ANE error 15 was the **wrong IOSurface factory**, not firmware |
| `AmiraniLabs/libane` | 6 | most active; implements matmul as conv1x1, claims 3× over MIL matmul |
| `royisme/qwen-ane-llm` | 1 | ANE-LM wrapped in an OpenAI-compatible server |
| `skyfallsin/ane.cpp` | 5 | continuing ANE-LM toward 4B+ |

## Negative and failure reports — the most valuable category

- **`compute_units=ALL` silently routes to GPU instead of ANE** on macOS 26.3, ~0 W ANE power — *the
  same silent fallback we hit on Granite fp32*.
- **W4 + ANE segfault** at coremltools 9.0; **fp16 softplus overflow**; **state-mutation compile
  failures** killing ANE lowering.
- **iOS 27 background-ANE entitlement change** — and a report that the **ANE is *not* revoked when an
  app backgrounds**, unlike the GPU (which kills llama.cpp/MLX). **79% throughput retained.**
- **Only 10 of 652 Core AI assets actually compile to the ANE**; the other 642 target the GPU.
  **4B-class models fail to load on iOS 27.0** (one `EXC_ARM_PAC_FAIL`, one 35-minute wedge).
- **Apple Watch S12 / Ultra 4 reboots** traced to an **ANE timeout** in `panic-full` logs.

## Independent ports of the model we ported

| | measured | URL |
| --- | --- | --- |
| **laya-mlx** | M3 Max **13.42 ms P50** (421M) / 7.39 ms (322M); 146.8 / 395.0 q/s; **63/63 parity** | <https://github.com/mizorewww/laya-mlx> |
| **laya-coreml (ANE)** | **4.98 ms P50**, 2.78–3.19× energy vs MLX, over 65,598 calls | <https://github.com/mizorewww/laya-coreml> |
| `afshinm/laya-mps` | **contrary result**: Core ML fp16 ~122 ms is **6× slower** than MPS fp32 on M5 Pro | <https://github.com/afshinm/laya-mps> |

**`laya-coreml` states its negatives explicitly** — a 96-token ANE cap, *"no long-context advantage"*
(a 1024-token graph takes 91.7 ms), and *"the claimed 10× target was NOT achieved."*
**Our S=1024 measurement was 106.8 ms — consistent with their 91.7 ms.**

## Talks with transcripts

- **WWDC26 324/325/326** — Core AI framework, authoring, integration · **full transcripts**
- **WWDC26 232** — *Run local agentic AI on the Mac using MLX* — **M5 Neural Accelerator 4× matmul**
- **WWDC26 233** — *distributed inference and training with MLX* — **4× M3 Ultra, 180 vs 600 tok/s**
- **Tech Talk 111432** — *Accelerate ML workloads with the M5 and A19 GPUs*
- **"CoreML Bypassed: Deconstructing the Silicon Constraints of Apple's Neural Engine"** — <https://www.youtube.com/watch?v=mbVFo2O4fWc>
- **Latent Space: *Jev — System One models for Prod, not God*** (CEO interview, full transcript) — <https://www.latent.space/p/jev>
- **"Laya (Free) vs Jev (Paid): Same Game, 4x Faster Winner"** — <https://www.youtube.com/watch?v=x1GFo1eG8d0>

**Not captioned:** the AI Engineer Diogo Almeida talk, Rob Shocks' JEV breakdown.

## What the sweep says we should do next

1. **Check the ANE DMA alignment finding against our graphs.** 2.4× for anyone, free to test.
2. **Read `apple/coreai-models`' agent skills** — it is the upstream we forked and it moved today.
3. **Batched prefill (11.3×)** is worth knowing before we design anything multi-request.
4. **Keep training on MPS, not the ANE** — and note Apple's own sanctioned path is **MLX distributed**
   (WWDC26 233), not ANE training.
5. **Our numbers agree with the independent ports**, which is the useful kind of confirmation.
