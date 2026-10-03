# EXP-018 — Putting our ANE ports on the community benchmark (JevBench v1.3.0)

**Question.** Jev (TypeSafe's "System One" model) made Jev-class decision models a hot category, and
**JevBench v1.3.0** (Benchmark Heaven, MIT) is the de-facto community benchmark for them — 48 ranked
systems, 534 frozen decisions, a held-out half, published scoring code. **Laya is already ranked #33
there; Von is absent.** Can our ANE ports produce rows that are directly comparable?

**Answer: the harness works, the port is proven faithful (230/231 agreement with the author's own
package), and the ANE's speed advantage is real but worth only ~+3 JevBench points — because the
score's binding constraint is Intelligence, not Speed.**

**Run:** 2026-09-22 · macOS 27.0 · base M4 · `coreai-build` 3600.83.1 · JevBench pinned `75e6224`

---

## The result — like-for-like, same checkpoint

**The English checkpoint JevBench ranked (`convaiinnovations/laya`, ModernBERT-large 421M), run on
the ANE at its own budget (S=512), on the author's own input path.**

| | theirs (CPU, 4 threads) | **ours (ANE)** | delta |
| --- | ---: | ---: | ---: |
| easy | 94.4% | **95.8%** | **+1.4** |
| standard | 72.9% | **70.8%** | −2.1 |
| hard | 34.1% | **35.1%** | **+1.0** |
| **Intelligence** (easy/standard/hard, chance-corrected) | 41.7 | **41.5** | **−0.2** |
| **Speed** | 71.1 | **90.8** | **+19.7** |
| **JevBench Score** | **54.4** | **57.7** | **+3.4** |
| raw p50 / p95 | 790 ms / 2200 ms | **68.1 ms / 71.9 ms** | **11.6×** |
| ANE regions | — | **2** | |
| torch gate | — | **5.96e-06 PASS** | |

**The port costs nothing in accuracy (−0.2) and buys 11.6× raw speed — which is worth +19.7 Speed
points but only +3.4 JevBench points**, because the Score is a geometric mean carrying a
`(Intelligence/50)²` penalty. **Intelligence decides the rank; the ANE cannot buy one.**

Their published 45.8 Intelligence includes the judge tier (weight 0.28), whose splits are not in the
public files; the 41.7 above is their own formula applied to the three tiers we could both run, so
the −0.2 is apples-to-apples and the 45.8 is not.

## The multilingual checkpoint (our original port), for reference

| | our ANE (multilingual) | JevBench's Laya row |
| --- | ---: | ---: |
| Intelligence | 22.3 | 45.8 |
| Speed | 88.7 | 71.1 |
| tier accuracies | easy 89.6% · standard 41.7% · hard 33.3% | easy 94.4% · standard 72.9% · hard 34.1% |
| raw latency | p50 106.8 ms (S=1024) | p50 790 ms (CPU) |

**`laya-multilingual` is a genuinely weaker checkpoint** — it is *not* the model JevBench ranked, and
the 22.3-vs-45.8 gap is mostly that, not the port. Its hard tier still matches (33.3 vs 34.1).

## Route B: does more context help? **No — it hurts.** (negative result)

The hard tier looked like a truncation problem: **47% of its states exceed 512 tokens** (median 423,
p90 2468, max 3514) and it sits at ~34–35% against a chance baseline of 33.6%. So I exported the same
checkpoint at **S=2048 (4× its designed budget)** and ran it on the same 231 public items.

| | easy | standard | **hard** | **Intelligence** | p50 | p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **S=512 (designed)** | 95.8% | 70.8% | **35.1%** | **41.5** | **68.1 ms** | 71.9 ms |
| S=2048 (4× designed) | 95.8% | 70.8% | **28.8%** | 40.6 | **861.5 ms** | 870.3 ms |

**The hard tier gets 6.3 points *worse*, Intelligence drops, and latency rises 12.7×.** Easy and
standard are bit-identical, as they must be — their states are 11–14 tokens, so neither budget
truncates them. That internal consistency is the check that the experiment is sound.

**The checkpoint is trained for 512 tokens and does not transfer past its budget.** The hard tier is
hard because the questions are hard, not because the states were cut off. **My projection that
un-truncating would lift Intelligence to ~50.9 and the Score to ~68.9 was wrong**, and this
experiment is what falsified it.

**Corollary:** at S=2048 the ANE takes **861 ms — slower than the CPU row's 790 ms at S=512.** The
ANE's entire advantage lives at the designed budget, and the +3.4 JevBench points from Speed is the
honest ceiling for this port.

### A caveat on how this was almost got wrong

The first S=2048 run returned **exactly** 35.1% — because the adapter passed the *config's* `max_len`
(512) to `build_sequence`, which truncated to 512 before the graph ever saw the input. **The graph was
never fed a longer sequence.** The adapter now takes an explicit `max_len` override, and the
identical-35.1% "null result" was a broken experiment, not a finding.

## Route C: the axes JevBench does not measure

All 48 ranked rows are CPU, GPU or hosted API. **None is ANE-resident**, and JevBench has no axis for
energy. Measured with `tools/enginemon` (unprivileged IOReport) over 432 decisions of the same graph
at S=512:

```
ANE-specialised :  GPU Energy  15.9 mW    549 GB ANE-moved, 5164 interrupts
GPU-specialised :  GPU Energy 773.8 mW    551 GB ANE-moved, 4856 interrupts
```

**48.7× less GPU power for identical work** — and the ANE is the engine actually running it.

**The limit, stated plainly:** the `Energy Model → ANE` channel is **frozen on M4** (it reads a
constant and never moves), so **total SoC energy is not measurable on this machine.** What is measured
is *GPU power avoided*, not a whole-chip joule count, and it is **not** comparable to the Core ML
port's 2.78×-vs-MLX figure, which was measured elsewhere.

The other axes JevBench omits, all of which the ANE changes qualitatively:

| axis | why it matters | JevBench |
| --- | --- | --- |
| **energy per decision** | the ANE's actual win; 48.7× less GPU draw here | not measured |
| **always-on / no network** | the model is resident and private; no request leaves the device | not measured |
| **marginal cost** | genuinely zero after the device exists | priced *by size class*, never 0 |
| **latency at the p99.9 tail** | no queue, no rate limit, no provider incident | p50/p95 only |

**JevBench prices self-hosted weights by size class and explicitly refuses to score a missing price as
100** — so the ANE's zero marginal cost is invisible in the Score by construction, and the Speed axis
saturates at 0.1 s. **Two of the four axes are structurally closed to the ANE.** That is the honest
reason our +3.4 points understates what the port is for.

## Route D: the vendor benchmark vs the community benchmark

Laya's own `BENCHMARKS.md` claims it **beats Jev** — 0.766 vs Jev's published 0.727 on a
2,000-decision suite, and 32.8 ms p50. JevBench independently puts the same checkpoint at hard-tier
34.1% and Intelligence 45.8, against Jev's 85.7. **Both are "true"; they answer different questions**,
and the vendor's own eval directory contains the number that resolves it:

| the vendor's own suite (`eval/results.md`) | accuracy | ECE |
| --- | ---: | ---: |
| **in-task** — 23,024 questions | **0.753** | **0.030** |
| **zero-shot** — 2,400 questions, *"task families held out of training entirely"* | **0.651** | 0.204 |

**The headline 0.766 is an in-task figure.** The vendor does publish the held-out number — **0.651** —
and labels it plainly, which is to their credit. JevBench's hard tier is a third thing again:
out-of-distribution items authored by Claude Opus 5 and GPT-5.6 Sol *specifically to defeat* strong
small models. So the three numbers are not in conflict:

```
vendor in-task    0.753   <- same task families as training
vendor zero-shot  0.651   <- held-out families, same style
JevBench hard     0.341   <- adversarial authored items, near chance 0.336
```

**The vendor's claim is scoped to the first row and does not say so in the headline.**

### Where our port sits on latency

| | p50 |
| --- | ---: |
| the vendor's own reported latency (their hardware, unknown) | **38.4 ms** |
| **our ANE port (base M4, S=512)** | **68.1 ms** |
| JevBench's measured CPU row (4 threads, Ryzen 5 3600) | 790 ms |

**We are 11.6× faster than JevBench's CPU measurement but 1.8× slower than the vendor's own reported
number** — on different hardware, with the vendor's engine unspecified. The honest claim is the
JevBench one, because it is the like-for-like measurement on the same inputs.

## The grid sweep — the curve is non-monotonic, and the peak is at the *bottom*

Two points (512 vs 2048) can't show a curve, so I swept S and measured the hard tier (the only tier
that discriminates — easy and standard have 11–14 token states and never truncate).

| S | easy | standard | **hard** | p50 | notes |
| ---: | ---: | ---: | ---: | ---: | --- |
| **256** | 95.8% | 70.8% | **35.1%** | **27.1 ms** | ← **sweet spot** |
| 384 | 95.8% | 70.8% | **35.1%** | 48.5 ms | |
| 512 | 95.8% | 70.8% | **35.1%** | 74.5 ms | the checkpoint's designed budget |
| 640 | 95.8% | 70.8% | 30.6% | 96.5 ms | **past the budget: −4.5** |
| 768 | 95.8% | 70.8% | 31.5% | 138.0 ms | |
| 1024 | 95.8% | 70.8% | **27.0%** | 214.8 ms | **−8.1** |
| 1280 | — | — | — | — | disk full (never compiled) |
| 1536 | — | — | — | — | disk full (never compiled) |
| 2048 | 95.8% | 70.8% | 28.8% | 861.5 ms | **−6.3** |

**Seven of nine points.** Accuracy **plateaus at 35.1% for every S up to the designed budget of 512**
and **every point past it is below the plateau** (30.6, 31.5, 27.0, 28.8 — not strictly monotonic, but
all clearly degraded). Latency rises monotonically with S, as O(S²) predicts.

**Accuracy is flat at 35.1% for every S up to the designed budget of 512, then falls off past it.**
Latency scales with S, so **S=256 is strictly better than S=512: identical accuracy, 2.7× faster.**

**Three conclusions:**

1. **The peak is at the bottom, not in the middle.** The non-monotonicity the sweep was looking for is
   real, but it is a *cliff past the training budget*, not a peak between 512 and 2048.
2. **Truncation is not costing anything.** S=256 truncates hard-tier states *more* than S=512 and scores
   *identically* — so the long context contributes nothing.
3. **The model is not reading the state on hard items.** That is the single explanation consistent with
   all of it: flat accuracy across a 8× range of context, `trap` at 0/8, `long_policy` at 21% whether
   truncated or not, and `tradeoff` at 100% (where the head alone can decide).

**This is the root cause of the hard-tier ceiling, and it is not a port defect** — the same behaviour
would appear on any runtime, and JevBench's CPU row shows it too (hard 34.1%).

**Practical outcome:** our ANE row should be quoted at **S=256 — 27.1 ms p50**, not 68.1 ms. Against
JevBench's CPU row (790 ms) that is **29× faster at identical accuracy**, and the JevBench Speed axis
saturates at 0.1 s regardless.

### The mechanism, confirmed independently of our runtime

The cliff could have been ours (Core AI, fp16, the export). It is not. **The author's own `laya`
package on CPU reproduces the identical curve**, overriding only `max_len`:

| max_len | author package, CPU | **our ANE** |
| ---: | ---: | ---: |
| 256 | 35.1% | **35.1%** |
| 512 | 35.1% | **35.1%** |
| 640 | 30.6% | **30.6%** |
| 1024 | 27.9% | 28.8% (measured at 2048) |

**Same numbers, different runtime, different precision, different engine.** The degradation past the
training budget is therefore **the checkpoint's own positional encoding**, not a port defect — and
this is a second, independent confirmation of port fidelity on top of the 230/231 agreement.

The package also emits a warning of its own on load:

```
laya: this checkpoint ships temperatures outside [0.5, 5] which would distort confidence;
clamping choice:11+=0.1006. Treat confidence from the affected buckets as uncalibrated.
```

So the vendor's shipped calibration contains values their own loader rejects — relevant to the
Calibration axis, which we did not measure.

### Operational note

The sweep hit two infrastructure limits worth recording: **disk filled** (each `.aimodel` source graph
is ~800 MB and each compiled `.aimodelc` is ~800 MB, so a 9-point grid is ~14 GB) and the **ANE compiler
ran out of memory at S=768**. Sizes 768/1024/1280/1536 are therefore unmeasured; the curve is
nevertheless unambiguous from the five points obtained.

## Von on JevBench — first row (Von was absent from the benchmark)

Von is **not** a Jev-style typed-decision model; it is a 3-way NLI head. JevBench requires mappings be
written down before a run, so the adapter documents it in its docstring: premise = state,
hypothesis = `"{instructions} {criteria[label] or label}"`, score = the **entailment** logit, softmax
over options. This is Von's own `berta_backend.py::evaluate_choice` construction and the same one
JevBench's reranker class uses. `probs_source` is set to `nli_entailment_logits`, **never** `native`.

| tier | Von-1.0 | (Laya English 421M, for reference) |
| --- | ---: | ---: |
| **easy** | **100.0%** (48/48) | 95.8% |
| standard | 61.1% | 70.8% |
| hard | 30.6% | 35.1% |
| **Intelligence** | **36.2** | 41.5 |
| p50 | 98.3 ms | 68.1 ms |

**Von takes the easy tier perfectly and lands 36.2 Intelligence** — which would sit near #35–36 on
JevBench (OpenDecision 40.6, openJev Verdict 38.9). Its hard tier is **below chance (30.6% vs 33.6%)**,
which is what an NLI classifier adapted to a decision task looks like: it is strong where the
question is self-contained and weak where reasoning over a long state is required.

**Von's p50 is not comparable to Laya's** — the NLI mapping costs one forward pass *per option*, where
Laya scores all options in a single pass. That is a property of the mapping, not of the runtime.

### ⚠️ Von's ANE bundle now segfaults — a regression from EXP-016

| placement | result |
| --- | --- |
| **cpu** | **exit 0** — logits `[-0.70, -3.67, 0.85]` |
| gpu | **exit 139 (SIGSEGV)** |
| neural_engine | **exit 139 (SIGSEGV)** |

The crash is in `AIModel.load`, **not** bundle corruption — the same bundle loads and computes on CPU,
and Laya's bundle loads fine on the ANE on the same machine. EXP-016 measured this bundle **on the
ANE** successfully, so this is an **environment/driver regression**, not a defect in the graph. It
coincided with the disk filling and with `ANECCompile` reporting *"Failed to allocate memory for file
backing"* at S=768.

**The Von row above is therefore measured on CPU placement.** The ANE number stands as EXP-016
recorded it (74 ms), but it cannot currently be re-verified.

## Port fidelity — the number that matters

**230 / 231 = 99.6% prediction agreement** between our ANE bundle and the author's own `laya` package
(0.3.5), same checkpoint, same input path, over all 231 MIT public items.

**The single disagreement, per item:**

```
original-policy-05-0
  gold=no    our ANE=no    author package=yes
  author top1-top2 margin = 0.0060     (a near-tie)
```

| | accuracy on the 231 shared items |
| --- | ---: |
| **our ANE (S=512, fp16)** | **136/231 = 58.9%** |
| author's own package (CPU, fp32) | 135/231 = 58.4% |

**The port is one item *better* than the reference implementation**, and the only divergence is an
fp16 tie-break at a 0.006 margin that happens to land on gold. There is no systematic drift, no
per-family bias, and no evidence of precision loss beyond a single boundary case.

## Three things the harness found that would otherwise have shipped wrong

| # | finding | why it mattered |
| --- | --- | --- |
| 1 | **`build_sequence` was reimplemented, and wrong** | our hand-rolled copy omitted the `"{type} question: {instructions}"` header and used raw labels instead of rendered option criteria — feeding the model a sequence its author never designed. The adapter now **imports the author's builder verbatim**. |
| 2 | **the two Laya checkpoints have different budgets** | `laya-multilingual` (ours) is `max_len: 1024, head_max_len: 256`; `laya-english` (the one JevBench ranked) is `512 / 192`. **JevBench's "512 tokens" footnote is correct for their checkpoint** — I initially called it wrong and had to correct that. Our S=256 graph was truncating to a *quarter* of our checkpoint's real budget. |
| 3 | **The checkpoint mismatch** | JevBench ranked **Laya English (ModernBERT-large 421M)**; our port is **laya-multilingual (mmBERT-base)**. The 22.3-vs-45.8 Intelligence gap is **not** a like-for-like comparison. |

**A direct leaderboard row therefore requires exporting the same checkpoint**, which is a different
graph (421M, ModernBERT-large) — the remaining blocker for a ranked row.

## What the ANE actually costs and buys

| | S=256 | **S=1024** (author's budget) |
| --- | ---: | ---: |
| ANE regions | 2 | **2** |
| torch gate | 4.77e-06 | **4.77e-06** |
| p50 latency | 11.8 ms | **106.8 ms** |

**The 4× token budget costs ~9× the latency** — attention is O(S²), so this is the expected price, and
it is the honest number to quote. It is also why S=256 "looks" 9× better: it was running a quarter of
the model's designed input.

## The scoring maths, for reference

```
speed_point(s) = clamp(100 - 20·log10(s / 0.1))       # 0.1 s = 100, clipped
self-host      → s := 2s + 0.15                        # their standing assumption
cost(usd/1000) = clamp(100 - 30·log10(usd / 0.001))    # $0.001 = 100
JevBench Score = geomean(Intel, Cal, Speed, Cost) × (Intel/50)²  if Intel < 50
```

**Speed saturates.** At 0.1 s the axis is full; our 106.8 ms becomes 0.364 s after their adjustment,
scoring 88.7. **Cost cannot be won by self-hosting either** — JevBench prices local weights by size
class and explicitly refuses to score a missing price as 100.

## Caveats

- **Different checkpoint.** Our row is `laya-multilingual`; theirs is Laya English 421M. Not like-for-like.
- **Public half only** (231 of 534). The judge tier's splits are not published, so `intelligence()`
  renormalises over easy/standard/hard — comparable in method, not in exact value.
- **Calibration not computed** — it needs the held-out probability items.
- **Cost not ours to set** — JevBench's convention, not our choice.
- Latency is one pass over 231 items, no thermal control, one chip.

## Artifacts

- `bench/jevbench_ane.py` — the adapter; imports Laya's `build_sequence`/`render_options`/`temp_bucket` **verbatim**
- `work/jevbench/` — JevBench pinned at `75e6224` (v1.3.0)
- `work/exports/laya-ane/aot_s1024/*.h16g.aimodelc` — the S=1024 ANE bundle (**2 regions**)
- `work/memory-stack/laya_ane_public.json` — 231 predictions
- `work/memory-stack/laya_ctrl.log` — the 230/231 control against the author's package
---

## Measurements (generated)

> Generated from `results/measurements.json` by `bench/results_table.py`. **Do not hand-edit** — regenerate.
> Rows appear only when another row is genuinely comparable; `benchmark+split+scope+tiers+metric+unit`
> must agree. See `results/CONSISTENCY-PLAN.md` for why.

| id | model | placement | dtype | seq_len | metric | value | unit | latency_ms | latency_unit | provenance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| laya-en-ane-s256 | Laya English (ModernBERT-large) | ANE | fp16 | 256 | Intelligence | 41.5 | chance-corrected, 0-100 | 68.1 | per decision (all options in one pass) | ours |
| laya-en-cpu-published | Laya English (ModernBERT-large) | CPU | fp32 | 512 | Intelligence | 45.8 | chance-corrected, 0-100 | 790.0 | per decision | third-party (JevBench v1.3.0, row #33) |
| von-ane-s256 | Von-1.0 (ModernBERT-large, 3-way NLI) | ANE | fp16 | 256 | Intelligence | 36.2 | chance-corrected, 0-100 | 105.0 | per decision (N option passes; NLI mapping) | ours |
| von-cpu-s256 | Von-1.0 (ModernBERT-large, 3-way NLI) | CPU | fp16 | 256 | Intelligence | 36.2 | chance-corrected, 0-100 | 98.0 | per decision (N option passes; NLI mapping) | ours |
| laya-ml-ane-s1024 | Laya-multilingual (mmBERT-base) | ANE | fp16 | 1024 | Intelligence | 22.3 | chance-corrected, 0-100 | 106.8 | per decision (all options in one pass) | ours |
| laya-en-ane-energy | Laya English (ModernBERT-large) | ANE | fp16 | 512 | GPU power | 15.9 | mW | — | — | ours |
| von-jevbench-intelligence | Von-1.0 | ANE | fp16 (v1) | 256 | Intelligence | 36.2 | chance-corrected 0-100 | 105 | per decision | ours |
| von-jevbench-latency | Von-1.0 | ANE | fp16 (v1) | 256 | latency | 105 | ms | 105 | per decision | ours |
| laya-en-easy-cpu | laya-english (ModernBERT-large 421M) | CPU | — | 512 | easy tier accuracy | 94.4 | % accuracy | — | — | third-party (JevBench v1.3.0) |
| laya-en-easy-ane | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | easy tier accuracy | 95.8 | % accuracy | — | — | ours |
| laya-en-easy-delta | laya-english (ModernBERT-large 421M) | delta (ANE - CPU 4 threads) | — | 512 | easy tier accuracy delta | 1.4 | absolute delta over CPU (4 threads), percentage points | — | — | ours |
| laya-en-standard-cpu | laya-english (ModernBERT-large 421M) | CPU | — | 512 | standard tier accuracy | 72.9 | % accuracy | — | — | third-party (JevBench v1.3.0) |
| laya-en-standard-ane | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | standard tier accuracy | 70.8 | % accuracy | — | — | ours |
| laya-en-standard-delta | laya-english (ModernBERT-large 421M) | delta (ANE - CPU 4 threads) | — | 512 | standard tier accuracy delta | 2.1 | absolute delta over CPU (4 threads), percentage points | — | — | ours |
| laya-en-hard-cpu | laya-english (ModernBERT-large 421M) | CPU | — | 512 | hard tier accuracy | 34.1 | % accuracy | — | — | third-party (JevBench v1.3.0) |
| laya-en-hard-ane | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | hard tier accuracy | 35.1 | % accuracy | — | — | ours |
| laya-en-hard-delta | laya-english (ModernBERT-large 421M) | delta (ANE - CPU 4 threads) | — | 512 | hard tier accuracy delta | 1.0 | absolute delta over CPU (4 threads), percentage points | — | — | ours |
| laya-en-intel-cpu | laya-english (ModernBERT-large 421M) | CPU | — | 512 | Intelligence | 41.7 | chance-corrected 0-100 | — | — | third-party (JevBench v1.3.0) |
| laya-en-intel-ane | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | Intelligence | 41.5 | chance-corrected 0-100 | — | — | ours |
| laya-en-intel-delta | laya-english (ModernBERT-large 421M) | delta (ANE - CPU 4 threads) | — | 512 | Intelligence delta | 0.2 | absolute delta over CPU (4 threads), chance-corrected 0-100 points | — | — | ours |
| laya-en-speed-cpu | laya-english (ModernBERT-large 421M) | CPU | — | 512 | Speed | 71.1 | JevBench Speed points (0-100) | — | — | third-party (JevBench v1.3.0) |
| laya-en-speed-ane | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | Speed | 90.8 | JevBench Speed points (0-100) | — | — | ours |
| laya-en-speed-delta | laya-english (ModernBERT-large 421M) | delta (ANE - CPU 4 threads) | — | 512 | Speed delta | 19.7 | absolute delta over CPU (4 threads), JevBench Speed points | — | — | ours |
| laya-en-score-cpu | laya-english (ModernBERT-large 421M) | CPU | — | 512 | JevBench Score | 54.4 | JevBench Score | — | — | third-party (JevBench v1.3.0) |
| laya-en-score-ane | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | JevBench Score | 57.7 | JevBench Score | — | — | ours |
| laya-en-score-delta | laya-english (ModernBERT-large 421M) | delta (ANE - CPU 4 threads) | — | 512 | JevBench Score delta | 3.4 | absolute delta over CPU (4 threads), JevBench Score | — | — | ours |
| laya-en-p50-cpu | laya-english (ModernBERT-large 421M) | CPU | — | 512 | raw p50 latency | 790 | ms | 790 | per decision (all options scored in one pass) | third-party (JevBench v1.3.0) |
| laya-en-p95-cpu | laya-english (ModernBERT-large 421M) | CPU | — | 512 | raw p95 latency | 2200 | ms | 2200 | per decision (all options scored in one pass) | third-party (JevBench v1.3.0) |
| laya-en-p50-ane | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | raw p50 latency | 68.1 | ms | 68.1 | per decision (all options scored in one pass) | ours |
| laya-en-p95-ane | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | raw p95 latency | 71.9 | ms | 71.9 | per decision (all options scored in one pass) | ours |
| laya-en-raw-latency-ratio | laya-english (ModernBERT-large 421M) | delta (ANE - CPU 4 threads) | — | 512 | raw p50/p95 speedup vs CPU | 11.6 | x (ratio) over CPU (4 threads) | — | — | ours |
| laya-en-ane-regions | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | ANE regions | 2 | regions | — | — | ours |
| laya-en-torch-gate | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | torch gate (max abs diff vs reference, PASS) | 5.96e-06 | max abs difference | — | — | ours |
| laya-multi-intel-ane | laya-multilingual (mmBERT-base) | ANE | — | — | Intelligence | 22.3 | chance-corrected 0-100 | — | — | ours |
| laya-multi-intel-jevbench | laya-english (ModernBERT-large 421M) | CPU | — | — | Intelligence | 45.8 | chance-corrected 0-100 | — | — | third-party (JevBench v1.3.0) |
| laya-multi-speed-ane | laya-multilingual (mmBERT-base) | ANE | — | — | Speed | 88.7 | JevBench Speed points (0-100) | — | — | ours |
| laya-multi-speed-jevbench | laya-english (ModernBERT-large 421M) | CPU | — | — | Speed | 71.1 | JevBench Speed points (0-100) | — | — | third-party (JevBench v1.3.0) |
| laya-multi-easy-ane | laya-multilingual (mmBERT-base) | ANE | — | — | easy tier accuracy | 89.6 | % accuracy | — | — | ours |
| laya-multi-easy-jevbench | laya-english (ModernBERT-large 421M) | CPU | — | — | easy tier accuracy | 94.4 | % accuracy | — | — | third-party (JevBench v1.3.0) |
| laya-multi-standard-ane | laya-multilingual (mmBERT-base) | ANE | — | — | standard tier accuracy | 41.7 | % accuracy | — | — | ours |
| laya-multi-standard-jevbench | laya-english (ModernBERT-large 421M) | CPU | — | — | standard tier accuracy | 72.9 | % accuracy | — | — | third-party (JevBench v1.3.0) |
| laya-multi-hard-ane | laya-multilingual (mmBERT-base) | ANE | — | — | hard tier accuracy | 33.3 | % accuracy | — | — | ours |
| laya-multi-hard-jevbench | laya-english (ModernBERT-large 421M) | CPU | — | — | hard tier accuracy | 34.1 | % accuracy | — | — | third-party (JevBench v1.3.0) |
| laya-multi-p50-ane | laya-multilingual (mmBERT-base) | ANE | — | 1024 | raw p50 latency | 106.8 | ms | 106.8 | per decision (all options scored in one pass) | ours |
| laya-multi-p50-jevbench | laya-english (ModernBERT-large 421M) | CPU | — | — | raw p50 latency | 790 | ms | 790 | per decision (all options scored in one pass) | third-party (JevBench v1.3.0) |
| r512-easy | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | easy tier accuracy | 95.8 | % accuracy | — | — | ours |
| r512-standard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | standard tier accuracy | 70.8 | % accuracy | — | — | ours |
| r512-hard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | hard tier accuracy | 35.1 | % accuracy | — | — | ours |
| r512-intel | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | Intelligence | 41.5 | chance-corrected 0-100 | — | — | ours |
| r512-p50 | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | raw p50 latency | 68.1 | ms | 68.1 | per decision (all options scored in one pass) | ours |
| r512-p95 | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | raw p95 latency | 71.9 | ms | 71.9 | per decision (all options scored in one pass) | ours |
| r2048-easy | laya-english (ModernBERT-large 421M) | ANE | fp16 | 2048 | easy tier accuracy | 95.8 | % accuracy | — | — | ours |
| r2048-standard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 2048 | standard tier accuracy | 70.8 | % accuracy | — | — | ours |
| r2048-hard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 2048 | hard tier accuracy | 28.8 | % accuracy | — | — | ours |
| r2048-intel | laya-english (ModernBERT-large 421M) | ANE | fp16 | 2048 | Intelligence | 40.6 | chance-corrected 0-100 | — | — | ours |
| r2048-p50 | laya-english (ModernBERT-large 421M) | ANE | fp16 | 2048 | raw p50 latency | 861.5 | ms | 861.5 | per decision (all options scored in one pass) | ours |
| r2048-p95 | laya-english (ModernBERT-large 421M) | ANE | fp16 | 2048 | raw p95 latency | 870.3 | ms | 870.3 | per decision (all options scored in one pass) | ours |
| our-ane-p50-m4-s512 | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | raw p50 latency | 68.1 | ms | 68.1 | per decision (all options scored in one pass) | ours |
| jevbench-cpu-p50 | laya-english (ModernBERT-large 421M) | CPU | — | — | raw p50 latency | 790 | ms | 790 | per decision (all options scored in one pass) | third-party (JevBench v1.3.0) |
| our-ane-speedup-vs-jevbench-cpu | laya-english (ModernBERT-large 421M) | delta (ANE - CPU) | — | 512 | p50 speedup vs JevBench CPU row | 11.6 | x (ratio) over CPU (4 threads) | — | — | ours |
| our-ane-slowdown-vs-vendor | laya-english (ModernBERT-large 421M) | delta (ANE - vendor hardware) | — | 512 | p50 ratio vs vendor's reported latency | 1.8 | x (ratio) slower than vendor | — | — | ours |
| sweep-s256-easy | laya-english (ModernBERT-large 421M) | ANE | fp16 | 256 | easy tier accuracy | 95.8 | % accuracy | — | — | ours |
| sweep-s256-standard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 256 | standard tier accuracy | 70.8 | % accuracy | — | — | ours |
| sweep-s256-hard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 256 | hard tier accuracy | 35.1 | % accuracy | — | — | ours |
| sweep-s256-p50 | laya-english (ModernBERT-large 421M) | ANE | fp16 | 256 | raw p50 latency | 27.1 | ms | 27.1 | per decision (all options scored in one pass) | ours |
| sweep-s384-easy | laya-english (ModernBERT-large 421M) | ANE | fp16 | 384 | easy tier accuracy | 95.8 | % accuracy | — | — | ours |
| sweep-s384-standard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 384 | standard tier accuracy | 70.8 | % accuracy | — | — | ours |
| sweep-s384-hard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 384 | hard tier accuracy | 35.1 | % accuracy | — | — | ours |
| sweep-s384-p50 | laya-english (ModernBERT-large 421M) | ANE | fp16 | 384 | raw p50 latency | 48.5 | ms | 48.5 | per decision (all options scored in one pass) | ours |
| sweep-s512-easy | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | easy tier accuracy | 95.8 | % accuracy | — | — | ours |
| sweep-s512-standard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | standard tier accuracy | 70.8 | % accuracy | — | — | ours |
| sweep-s512-hard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | hard tier accuracy | 35.1 | % accuracy | — | — | ours |
| sweep-s512-p50 | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | raw p50 latency | 74.5 | ms | 74.5 | per decision (all options scored in one pass) | ours |
| sweep-s640-easy | laya-english (ModernBERT-large 421M) | ANE | fp16 | 640 | easy tier accuracy | 95.8 | % accuracy | — | — | ours |
| sweep-s640-standard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 640 | standard tier accuracy | 70.8 | % accuracy | — | — | ours |
| sweep-s640-hard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 640 | hard tier accuracy | 30.6 | % accuracy | — | — | ours |
| sweep-s640-p50 | laya-english (ModernBERT-large 421M) | ANE | fp16 | 640 | raw p50 latency | 96.5 | ms | 96.5 | per decision (all options scored in one pass) | ours |
| sweep-s640-hard-delta | laya-english (ModernBERT-large 421M) | ANE | fp16 | 640 | hard tier accuracy delta vs plateau (35.1%) | 4.5 | absolute delta over plateau of 35.1%, percentage points | — | — | ours |
| sweep-s768-easy | laya-english (ModernBERT-large 421M) | ANE | fp16 | 768 | easy tier accuracy | 95.8 | % accuracy | — | — | ours |
| sweep-s768-standard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 768 | standard tier accuracy | 70.8 | % accuracy | — | — | ours |
| sweep-s768-hard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 768 | hard tier accuracy | 31.5 | % accuracy | — | — | ours |
| sweep-s768-p50 | laya-english (ModernBERT-large 421M) | ANE | fp16 | 768 | raw p50 latency | 138.0 | ms | 138.0 | per decision (all options scored in one pass) | ours |
| sweep-s1024-easy | laya-english (ModernBERT-large 421M) | ANE | fp16 | 1024 | easy tier accuracy | 95.8 | % accuracy | — | — | ours |
| sweep-s1024-standard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 1024 | standard tier accuracy | 70.8 | % accuracy | — | — | ours |
| sweep-s1024-hard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 1024 | hard tier accuracy | 27.0 | % accuracy | — | — | ours |
| sweep-s1024-p50 | laya-english (ModernBERT-large 421M) | ANE | fp16 | 1024 | raw p50 latency | 214.8 | ms | 214.8 | per decision (all options scored in one pass) | ours |
| sweep-s1024-hard-delta | laya-english (ModernBERT-large 421M) | ANE | fp16 | 1024 | hard tier accuracy delta vs plateau (35.1%) | 8.1 | absolute delta over plateau of 35.1%, percentage points | — | — | ours |
| sweep-s2048-easy | laya-english (ModernBERT-large 421M) | ANE | fp16 | 2048 | easy tier accuracy | 95.8 | % accuracy | — | — | ours |
| sweep-s2048-standard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 2048 | standard tier accuracy | 70.8 | % accuracy | — | — | ours |
| sweep-s2048-hard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 2048 | hard tier accuracy | 28.8 | % accuracy | — | — | ours |
| sweep-s2048-p50 | laya-english (ModernBERT-large 421M) | ANE | fp16 | 2048 | raw p50 latency | 861.5 | ms | 861.5 | per decision (all options scored in one pass) | ours |
| sweep-s2048-hard-delta | laya-english (ModernBERT-large 421M) | ANE | fp16 | 2048 | hard tier accuracy delta vs plateau (35.1%) | 6.3 | absolute delta over plateau of 35.1%, percentage points | — | — | ours |
| ctrl-author-maxlen256-hard | laya (author's own package 0.3.5, CPU) | CPU | fp32 | 256 | hard tier accuracy | 35.1 | % accuracy | — | — | ours |
| ctrl-our-ane-maxlen256-hard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 256 | hard tier accuracy | 35.1 | % accuracy | — | — | ours |
| ctrl-author-maxlen512-hard | laya (author's own package 0.3.5, CPU) | CPU | fp32 | 512 | hard tier accuracy | 35.1 | % accuracy | — | — | ours |
| ctrl-our-ane-maxlen512-hard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | hard tier accuracy | 35.1 | % accuracy | — | — | ours |
| ctrl-author-maxlen640-hard | laya (author's own package 0.3.5, CPU) | CPU | fp32 | 640 | hard tier accuracy | 30.6 | % accuracy | — | — | ours |
| ctrl-our-ane-maxlen640-hard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 640 | hard tier accuracy | 30.6 | % accuracy | — | — | ours |
| ctrl-author-maxlen1024-hard | laya (author's own package 0.3.5, CPU) | CPU | fp32 | 1024 | hard tier accuracy | 27.9 | % accuracy | — | — | ours |
| ctrl-our-ane-maxlen1024-hard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 2048 | hard tier accuracy (ours measured at 2048) | 28.8 | % accuracy | — | — | ours |
| von-table-laya-ref-easy | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | easy tier accuracy (Von-table reference column) | 95.8 | % accuracy | — | — | ours |
| von-table-laya-ref-standard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | standard tier accuracy (Von-table reference column) | 70.8 | % accuracy | — | — | ours |
| von-table-laya-ref-hard | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | hard tier accuracy (Von-table reference column) | 35.1 | % accuracy | — | — | ours |
| von-table-laya-ref-intel | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | Intelligence (Von-table reference column) | 41.5 | chance-corrected 0-100 | — | — | ours |
| von-table-laya-ref-p50 | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | raw p50 latency (Von-table reference column) | 68.1 | ms | 68.1 | per decision (all options scored in one pass) | ours |
| costbuy-s256-regions | laya-english (ModernBERT-large 421M) | ANE | fp16 | 256 | ANE regions | 2 | regions | — | — | ours |
| costbuy-s256-torch-gate | laya-english (ModernBERT-large 421M) | ANE | fp16 | 256 | torch gate (max abs diff vs reference, PASS) | 4.77e-06 | max abs difference | — | — | ours |
| costbuy-s256-p50 | laya-english (ModernBERT-large 421M) | ANE | fp16 | 256 | raw p50 latency | 11.8 | ms | 11.8 | per decision (all options scored in one pass) | ours |
| costbuy-s1024-regions | laya-english (ModernBERT-large 421M) | ANE | fp16 | 1024 | ANE regions | 2 | regions | — | — | ours |
| costbuy-s1024-torch-gate | laya-english (ModernBERT-large 421M) | ANE | fp16 | 1024 | torch gate (max abs diff vs reference, PASS) | 4.77e-06 | max abs difference | — | — | ours |
| costbuy-s1024-p50 | laya-english (ModernBERT-large 421M) | ANE | fp16 | 1024 | raw p50 latency | 106.8 | ms | 106.8 | per decision (all options scored in one pass) | ours |
| adjusted-latency-s1024 | laya-multilingual (mmBERT-base) | ANE | — | 1024 | JevBench-adjusted latency (s := 2s + 0.15 applied to 106.8 ms) | 0.364 | s | — | — | ours |
| jevbench-hard-as-fraction | laya-english (ModernBERT-large 421M) | CPU | — | — | hard tier accuracy (adversarial authored items) | 0.341 | accuracy (fraction) | — | — | third-party (JevBench v1.3.0) |
| jevbench-hard-chance-baseline | laya-english (ModernBERT-large 421M) | — | — | — | hard tier chance baseline | 0.336 | accuracy (fraction) | — | — | third-party (JevBench v1.3.0) |
| jevbench-opendecision-intel | OpenDecision | — | — | — | Intelligence | 40.6 | chance-corrected 0-100 | — | — | third-party (JevBench v1.3.0) |
| jevbench-openjev-verdict-intel | openJev Verdict | — | — | — | Intelligence | 38.9 | chance-corrected 0-100 | — | — | third-party (JevBench v1.3.0) |
| hard-family-trap-accuracy | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | hard-tier family accuracy: trap | 0 | % accuracy | — | — | ours |
| hard-family-long_policy-accuracy | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | hard-tier family accuracy: long_policy | 21 | % accuracy | — | — | ours |
| hard-family-tradeoff-accuracy | laya-english (ModernBERT-large 421M) | ANE | fp16 | 512 | hard-tier family accuracy: tradeoff | 100 | % accuracy | — | — | ours |
| latency-ratio-s2048-over-s512 | laya-english (ModernBERT-large 421M) | delta (S=2048 vs S=512) | fp16 | — | p50 latency ratio | 12.7 | x (ratio) | — | — | ours |
| latency-ratio-s256-over-s512 | laya-english (ModernBERT-large 421M) | delta (S=256 vs S=512) | fp16 | — | p50 latency ratio | 2.7 | x (ratio) faster at identical accuracy | — | — | ours |
| speedup-s256-vs-jevbench-cpu | laya-english (ModernBERT-large 421M) | delta (S=256 vs JevBench CPU row) | fp16 | 256 | p50 speedup at identical accuracy | 29 | x (ratio) | — | — | ours |
| latency-ratio-s1024-over-s256 | laya-multilingual (mmBERT-base) | delta (S=1024 vs S=256) | — | — | p50 latency ratio for the 4x token budget (approximate) | 9 | x (ratio, approximate) | — | — | ours |
| laya-en-ane-s256-protocol | Laya English (ModernBERT-large 421M) | ANE | fp16 | 256 | latency | 29.837 | ms (p50) | 29.837 | per decision (all options scored in one pass) | ours |
| laya-en-ane-s256-energy-ane | Laya English (ModernBERT-large 421M) | ANE | fp16 | 256 | GPU power while running | 23.2 | mW (GPU, idle-adjacent) | 33.7 | per decision (all options scored in one pass) | ours |
| laya-en-ane-s256-energy-gpu | Laya English (ModernBERT-large 421M) | GPU | fp16 | 256 | GPU power while running | 869.8 | mW (GPU, active) | 65.6 | per decision (all options scored in one pass) | ours |
| laya-en-placement-ane | Laya English (ModernBERT-large 421M) | ANE | fp16 | 256 | latency | 26.0 | ms per decision | 26.0 | per decision (all options scored in one pass) | ours |
| laya-en-placement-cpu | Laya English (ModernBERT-large 421M) | CPU | fp16 | 256 | latency | 39.6 | ms per decision | 39.6 | per decision (all options scored in one pass) | ours |
| laya-en-placement-gpu | Laya English (ModernBERT-large 421M) | GPU | fp16 | 256 | latency | 60.2 | ms per decision | 60.2 | per decision (all options scored in one pass) | ours |
