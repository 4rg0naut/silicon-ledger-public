# Von's ANE load crash — RESOLVED: it was disk space, not a compiler bug

## The answer

**The `.aimodelc` was written while the disk was full and came out incompletely written.** It was the
**correct size** (758 MB — identical to a good bundle), so no size check caught it, and it failed only
at `load_function` with a **diagnostic-free SIGSEGV**.

Re-exported and re-AOT'd with **35 GiB free**, the identical code path produces a bundle that works:

```
von-1.0_v1_float16_s256_ane.h16g.aimodelc:  exit=0   INFERENCE OK [-0.7026, -3.668, 0.8477]
von-1.0_v1_float16_s256_ane.aimodel:        exit=0   INFERENCE OK [-0.7026, -3.668, 0.8477]

reproducibility: 5/5 consecutive loads OK   (was 0/8 with the disk-full bundle)
```

The logits match the CPU reference exactly.

## What this corrects

**Three earlier hypotheses, all wrong:**

| hypothesis | verdict |
| --- | --- |
| ODIE compiler defect / `coreai-pre-compilation-rewrite` bug | **wrong** — no compiler bug; the artifact was truncated |
| `AIModel.load` crashes | **wrong** — load always succeeded; `load_function` failed |
| driver regression from EXP-016 | **wrong** — nothing regressed; the disk filled |

**And one workaround that was never a fix:** loading the `.aimodel` source instead of the AOT bundle.
That appeared to work only because the source path re-specializes on device, sidestepping the corrupt
artifact. **The AOT path works fine — with adequate disk.**

**The real chain:** the disk filled → a Time Machine local snapshot pinned every freed block → AOT
compiles failed with `No space left on device` → one compile wrote a same-size-but-corrupt bundle →
Von segfaulted at `load_function` with no diagnostic → I spent a long investigation on the wrong cause.

## The operational lesson

**A disk-full AOT can produce a correctly-sized, corrupt bundle.** `find -name '*ANE_region*' | wc -l`
returns a healthy count, the file size is right, and `coreai-build` exits 0. **Only a load proves it.**
`bench/aot_verify.sh` now wraps the compile: it checks free space before, ANE region count after, and
prints the bundle hash — the hash is the cheap thing to record and compare.

## The original investigation, kept for the record

The sections below are the research as it stood when the cause was believed to be a compiler bug. They
are retained because the *method* was sound (elimination by test, staged loading, `faulthandler`) and
because two of the findings remain useful. The conclusions in them are superseded.

**Trigger.** `Von-1.0`'s `.aimodelc` segfaults **in `m.load_function("main")`** — *not* in
`AIModel.load`, which returns successfully. It works on CPU placement. Laya's bundle, same machine,
same runtime, runs on both accelerated placements.

**The crash site, isolated by staging the load:**

```
STAGE1 loading
STAGE2 loaded, getting fn
   <- CRASH (never reaches STAGE3)
```

This also explains an apparent contradiction: a load-only script *succeeds* on Von's bundle. It never
calls `load_function`, so it never reaches the crash.

`load_function` is where the AOT specialization is materialised into an executable function — which is
the compile path the knowledge base's `coreai-pre-compilation-rewrite` entry describes.

**The exact frame, from `faulthandler`:**

```
Fatal Python error: Segmentation fault
Current thread:
  File ".../site-packages/coreai/runtime/_aimodel.py", line 86 in load_function
  File "/tmp/von_fh2.py", line 14 in <module>

Extension modules: numpy..., coreai.runtime._coreai_runtime_os,
                   odie_runner.coreai_runtime._coreai_runtime_os, PIL._imaging
```

**`coreai/runtime/_aimodel.py:86` inside `load_function`, with the `odie_runner` runtime loaded** — ODIE
being the compiler the knowledge base entry names (`libODIECompiler … CompileForDelegates`). So Von's
graph reaches the ODIE compile inside `load_function` and dies there; Laya's graph does not.

## 1. The pull request

**`john-rocky/coreai-model-zoo#36`** — *"granite-embedding-97m: the Neural Engine result for this model
(base M4)"*.

| | |
| --- | --- |
| state | **open** |
| head | `4rg0naut:granite-embedding-ane-m4` @ `055ded4` |
| base | `john-rocky:main` @ `347393e` |
| **comments** | **0** |
| **reviews** | **0** |
| created | 2026-09-20T20:02:25Z |

**There is no review feedback to act on.** The PR body is our own write-up.

## 2. What the PR body already told us, and how it reframes the bug

> **`--compute` cannot override an AOT bundle.** The fp16 `.aimodelc` uses the ANE under both
> `--compute neuralEngine` (101.6 GB moved) and `--compute gpu` (91.2 GB); only `cpuOnly` drops it to
> 0 interrupts. **Placement is baked at compile time.**

So passing `specialization_options` at load is *redundant* — and it is not what distinguishes Von from
Laya, since both are loaded the same way and only one crashes. Tested and eliminated below.

## 3. The knowledge base has the matching known bug

`knowledge/coreai-error-index.md` § *"SIGSEGV in coreai-pre-compilation-rewrite"*:

> `program.optimize()`, **the Python runtime's `AIModel.load`**, and `xcrun coreai-build compile` **all
> segfault on the same graph**: the pass is shared by every compile path.
> ```
> faulthandler: coreai/_compiler/_transforms/passes.py:261 apply_passes_sync <- coreai/authoring/asset.py:230 optimize
> ```
> **Verified cause:** a block emits a **degenerate all-zero constant-mask subgraph** that the
> `coreai-pre-compilation-rewrite` pass segfaults on.
> **Fix:** an output-identical mask workaround — **the mask is constant; build it outside the forward.**

**This matches our symptom exactly** — SIGSEGV inside `AIModel.load`, no diagnostic, no partial output.

**What I have not established:** that Von's graph actually contains that degenerate subgraph. Both
exports build their masks from the `attention_mask` *input*, so neither is trivially constant-foldable,
and Von's own `prog.optimize()` call **succeeded** during export (the asset saved). So the index's entry
is a **strong lead, not a proven cause**. The decisive test is to run `optimize()` on Von's exported
program under `faulthandler` and look for `passes.py:261` in the trace.

## 4. Eliminated by test

| hypothesis | test | result |
| --- | --- | --- |
| **crash in `AIModel.load`** | staged load with STAGE prints | **load returns; crash is in `load_function`** → corrected |
| system / driver state | Laya on **ANE and GPU** | works → **refuted** |
| stale or corrupt bundle | fresh v1 export + AOT | segfaults too → **refuted** |
| the v1 fp32-ism variant | fresh **v0** export (31 regions) | segfaults too → **refuted** |
| `specialization_options` misuse | `SpecializationOptions.default()` | segfaults too → **refuted** |
| `expectFrequentReshapes` | not exposed in the Python runtime | **untestable here** |
| memory pressure | `memory_pressure` | 78% free → **refuted** |

| | neural_engine | gpu | cpu |
| --- | --- | --- | --- |
| Von v1 (fresh, old, default opts) | SIGSEGV | SIGSEGV | **OK** |
| Von v0 (fresh, 31 regions) | SIGSEGV | SIGSEGV | — |
| **Laya s256** | **OK** | **OK** | — |

## 5. Other findings in the knowledge base worth carrying

- **`expectFrequentReshapes` on a fixed-shape graph kills the AOT bundle** — the runtime abandons the
  AOT specialization, compiles on device, and segfaults in the MPSGraph AICode compiler with *no error
  string*. Swift-only; not exposed in this Python runtime.
- **Architecture names track the device identifier, not the marketing name** — M4 Max is `h16c`;
  `h16g` raises RuntimeError there. Our base M4 is `h16g`, confirmed by `coreai-build inspect`.
- **`coreai-build compile` exits 0 for ANY requested architecture** — a successful compile does **not**
  validate the arch choice; only a device load does.
- **A bundle can silently fall back**: a failed ANE compilation yields exit 0, an empty `ErrorList`, and
  a `main-<arch>-delegates/` holding only `MPSGraph`. Detect it with
  `find <x>.aimodelc -name '*ANE_region*' | wc -l`.
- **`xctrace`'s `ane-hw-intervals` is blind to Core AI graphs** (0 intervals, while a Core ML control in
  the same session logs 1310) — corroborates our EXP-004 result, and is why `tools/enginemon` exists.

## 6. The fix — and it is not the mask

**The AOT-compiled `.aimodelc` is what crashes. The `.aimodel` source graph is fine.**

```
Von .aimodelc (AOT):    loading → load OK → load_function → SIGSEGV
Von .aimodel  (source): loading → load OK → load_function OK → INFERENCE OK
```

**Von runs on the ANE today by loading the source graph instead of the AOT bundle** — no graph change
needed. Load + on-device specialization costs **1.6 s** (the OS cache serves it after the first time).

**Von on the ANE, scored:**

| tier | **ANE (source path)** | CPU (AOT bundle) |
| --- | ---: | ---: |
| easy | **100.0%** (48/48) | 100.0% |
| standard | 59.7% | 61.1% |
| hard | 30.6% | 30.6% |
| **Intelligence** | **35.4** | 36.2 |
| **p50** | **246 ms** | **98 ms** |

Accuracy matches the CPU placement to within fp16 rounding. **But the ANE is 2.5× *slower* than the
CPU here — and the reason is the mapping, not the hardware.**

---

**End of the superseded material.** Everything below stands: §7 is the measured comparison, §8 the
Splash-thesis test, §9 the native-head scoping, §10 the open questions.

## 7. Why Von is slower on the ANE but Laya is 29× faster

This is the most useful comparison the session produced:

| | mapping | ANE vs CPU |
| --- | --- | --- |
| **Laya** | a **native typed-decision head** — all options scored in **one** forward pass | **27 ms vs 790 ms = 29× faster** |
| **Von** | an **NLI adaptation** — one forward pass **per option** | **246 ms vs 98 ms = 2.5× slower** |

**The ANE rewards putting every option into a single graph.** Laya's design does that; Von's NLI
mapping cannot, so it makes ~5 small calls per decision and pays the per-call overhead each time.
**The accelerator does not make a badly-shaped workload fast — it makes a well-shaped one much faster.**

That is also the answer to whether Von should be re-authored: a native single-pass decision head would
be worth more than any amount of ANE tuning.

## 8. Applying the Splash thesis to Von — what transfers, and what does not

Splash's recipe is *"the engine is built around the model: no generic runtime, no fallback path"*. The
testable half of that for us is **shape**: Von's NLI mapping makes one graph call per option, where
Laya's native head scores every option in a single pass. So I batched Von's graph — the only
batch-1 hardcodings were the mask `expand` and two attention reshapes — and exported it at **batch 8**
with all 8 options in one call.

| | shape | warm p50 | per option |
| --- | --- | ---: | ---: |
| Von, unbatched | N calls × S tokens | ~305 ms (5 opts) | ~61 ms |
| **Von, batched (8 in one call)** | **1 call × 8×S tokens** | **233 ms** | **29.2 ms** |
| **Laya** | **1 call × S tokens, options inside the sequence** | **27 ms total** | — |

**Batching is worth 2.1× throughput — and it is not the trick.** N sequences still cost N× one
sequence; batching only removes per-call overhead. **Laya's advantage is architectural: the options
share the sequence, so one pass of S tokens scores all of them.** That is why Laya is 29× faster on
the ANE and Von stays ~2× slower than its own CPU path even batched.

**So the transferable lesson is narrower and more useful than "specialise":** specialise the *shape so
the work collapses into one pass*, not merely into one call. Von needs a native decision head — Laya's
design — not a batched NLI loop.

**Numerics verified despite the gate gap.** The export gate runs on the **unbatched** shape only, so a
batched graph is not numerically checked by it. Verified separately: the batched graph's row 0 returns
`[-0.7026, -3.668, 0.8477]`, **identical** to the batch-1 reference. `probs_source` for Von remains
`nli_entailment_logits`, never `native`.

## 9. Scoping Von's native single-pass head

**The two designs, from the actual code:**

| | Laya (native) | Von (NLI adaptation) |
| --- | --- | --- |
| inputs | `input_ids`, `attention_mask`, **`selection [K,S]`**, `qtype` | `input_ids`, `attention_mask` |
| options | **marker tokens inside one sequence** | one sequence **per option** |
| readout | `m = selection @ h` — one-hot matmul replaces `torch.gather` | mean-pool → dense → GELU → LayerNorm → `classifier(1024→3)` |
| cost | **one pass of S tokens** | **N passes of S tokens** |

**What a native head needs, and what we already have:**

- **The architecture is already proven** — Laya's `selection @ h` pattern is in `export_laya_ane.py` and
  is ANE-legal; it exists precisely because `torch.gather` is a data-dependent index op Apple's rules
  reject. Building the same shape for Von is a day's work, no new machinery.
- **Von's trained head is directly reusable.** `classifier(1024→3)` + `head_dense` + `head_norm`
  operate on a 1024-dim vector. In a marker-based sequence, that vector is simply the hidden state
  **at each option's marker position** instead of a pooled sequence. **No new weights, no new
  supervision to make the graph run.**
- **What is *not* free is accuracy.** Von's head was trained on **mean-pooled (premise, hypothesis)
  pairs**. Marker-position hidden states are a different distribution, so the re-architecture would
  need a fine-tuning pass to recover the 61.1% standard / 30.6% hard it currently holds. **That needs
  Von's training data, which we do not have** — it is not released.

**The honest conclusion:** the single-pass head is **cheap to build and expensive to make accurate**.
The speed is predictable from Laya's measured result — one pass instead of N is the difference between
Laya's 29× ANE advantage and Von's current ~1× (105 ms ANE vs 98 ms CPU). But shipping it would mean
recovering accuracy without the original supervision, which is a training problem, not a porting one.

**What that means for the current result:** Von's ANE row (Intelligence 36.2, p50 105 ms) is the honest
ceiling for the *adapted* model. It matches the CPU row exactly — the port is faithful — but the NLI
mapping is what keeps it from being fast. **The accelerator is not the constraint; the mapping is.**

## 10. Open questions

1. ~~**Re-AOT Von's bundle and check whether the crash persists.**~~ **DONE — it was disk space.** With
   35 GiB free the same export + AOT produces a bundle that loads 5/5, and the AOT path is **2.3×
   faster to load** than the source-path workaround (105 ms vs 246 ms per decision).
2. ~~**If it persists, keep the source path.**~~ **Superseded** — the source path was a workaround for a
   truncated artifact, not a fix. Use the AOT bundle.
3. **The real win is a native head**: see §9 for the scoping — cheap to build, expensive to make
   accurate without Von's training data.
4. ~~**Fix the export gate** to validate the batched shape when `--batch > 1`.~~ **DONE.** The gate now
   also compares the batched graph against batch-1 and checks the row spread, since every row receives
   identical input and must therefore reproduce the same result. Verified on the batch-8 export:
   `|batched - batch1| = 2.38e-06`, `row spread = 0.00e+00`, PASS. A `--batch > 1` export can no longer
   ship numerically unchecked.
