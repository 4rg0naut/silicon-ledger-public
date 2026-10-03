# ANE layer — the winner, and an important correction

**Selected on quality:** Von-1.0 (70% exact, 75% yes/not) over LettuceDetect v2 (62%/66%) and
ModernCE-large-nli (8%/25%, broken).

**Ported and measured already** — EXP-016, 2026-09-22, base M4, macOS 27.0:

| | |
| --- | --- |
| AOT compile (ANE, h16g) | exit 0, 5 s |
| **ANE residency** | **3 regions, 0 GPU, 0 CPU — full** (first build was 31 regions; the fp32-ism ladder took it to 3) |
| Argmax vs HF fp32 | correct on every case |
| Probability error | ≤ 0.33 points worse case |
| **Latency** | **24 ms/decision** ANE vs **39 ms** GPU — the ANE is faster |

Re-running the harness today fails on a stale path (`aot_h16g_ane/` vs the actual `aot/`) and a
`CoreAIDelegates.AIModelCacheError error 3` — the known OS-27-beta driver issue that requires GPU
serialisation. The existing measurements stand; the harness needs its path fixed before it can be
re-run.

## The correction — "already on the ANE" does not mean "free"

An earlier statement in this session said the optimisation step costs nothing because the winner is
already ANE-resident. **That was wrong, and EXP-016 already contained the reason:**

> *"On JevBench's suite the same bundle measures **105 ms/decision**, matching the CPU row exactly.
> Von's NLI mapping makes one pass **per option**; Laya's native head scores all options in one,
> which is why **Laya is 29× on the ANE and Von is ~1×**."*

| design | passes for a 3-way decision | cost |
| --- | --- | --- |
| **Von (NLI cross-encoder)** | **3** — the passage is the premise and each option becomes a hypothesis | 105 ms measured |
| **Laya-style native head** | **1** — all options scored in a single pass | ~29× faster |

**So residency is not the same as efficiency.** A model can be fully on the ANE and still be
structurally expensive, because the *architecture* decides how many passes an answer needs.

## What this changes

**Keep Von for what it is** — a pairwise entailment model, where one premise and one hypothesis is
exactly the job. It won this layer on quality and it is genuinely good at that task.

**But a validator in the final pipeline should be a native-head decision model**, not an NLI
cross-encoder wrapping one. That means:

- the groundedness task (passage + claim → yes/partial/no) should be re-expressed as a **single-pass
  multi-option decision** and trained as such
- we have both halves: Laya's native-head architecture (already ported, 26 ms at S=256 on the ANE)
  and now 55 hand-verified training triples
- the 29× is the prize, and it is an architecture choice, not a porting problem

This is the same lesson the whole evaluation has been circling: **different tools for different
shapes of question.** NLI for pairs. A native decision head for options. They are not
interchangeable, and picking the wrong one costs an order of magnitude.