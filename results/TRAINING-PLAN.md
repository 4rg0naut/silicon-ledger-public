# Training our own decision model — the basic steps

**Goal:** a 150M-class decision model, ours, that drops onto the ANE at the 26 ms we already achieve.

**Why this is now worth doing:** a 149.6M model trained in **8.8 hours on a GTX 1660 Ti** (6 GB, no
tensor cores) beat a 421M model on that model's own benchmark. The entry cost collapsed. We have the
inference half built; this is the supply half.

---

## What we already have vs what's missing

| | status |
| --- | --- |
| **base encoders** | ✅ mmBERT-base and ModernBERT-class already ported to the ANE |
| **the head** | ✅ marker-pointer, all options in one pass — `HeadLayer` in `bench/export_laya_ane.py` |
| **the sequence format** | ✅ `[CLS] <type> instructions [SEP] [MASK] opt0 [MASK] opt1 … [SEP] state [SEP]` |
| **the export path to the ANE** | ✅ gate + AOT + region count, all proven |
| **the measurement** | ✅ 898 records, JevBench adapters, generated tables |
| **the calibration fix** | ✅ correctness head, −69% ECE, no retrain |
| **training data** | ✅ **`LocalLLaMA/typed-decisions`** — Apache-2.0, 1,200 train + 400 test rows, with expert-panel distributions |
| **a training loop** | ❌ **this is the only real gap** |
| **a training harness** | ❌ but the reference build is public (`verdict2/train.py` in the openJev-verdict-2.0 repo) |

**The gap is one script, not a research problem.**

---

## The steps

### 1. Pick the base — ModernBERT-base or mmBERT-base, ~150M

`verdict-2.0` deliberately **stopped at Base and said why on the record**: pre-registered gate was
dev accuracy ≥ 0.760 and Brier ≤ 0.120 *for the shipping model*; Base delivered 0.785 / 0.0639 and had
converged (final four epochs oscillating inside half a point). Large needed 8-bit AdamW **and**
gradient checkpointing to fit 6 GB at all, and would have taken 14–18 hours.

**We should start at Base for the same reason**, and because 150M is what the ANE handles comfortably.

### 2. Get the data

`LocalLLaMA/typed-decisions`, Apache-2.0 — four workflows, `state` + `questions` + `gold` +
`label_agreement` + `outcome__probabilities`. **The gold is a distribution, not a label** — that
matters for the loss (step 4) and is the whole reason the two-channel problem exists.

### 3. Build the sequences

Use **Laya's exact builder**, which we already import verbatim in `bench/jevbench_ane.py`. One
sequence holds every option as a `[MASK]` marker; the model reads the hidden state at each marker.

**Do not invent a format.** The marker layout is what makes it single-pass, and single-pass is what
makes it 26 ms on the ANE instead of Von's per-option loop.

### 4. The losses — three, and each fixes a named failure

| loss | for | what it fixes |
| --- | --- | --- |
| soft cross-entropy + **Brier** | choice | the base objective, and probability quality |
| **Ranked Probability Score** | score/ordinal | predicting level 1 when truth is 5 must cost more than predicting 4 |
| **Permutation-KL** | all | score a shuffled-option twin, add the symmetric KL — kills option-order sensitivity |

**Permutation-KL is not optional.** Our own JevBench work found option-order sensitivity in exactly
this model class, and `verdict-2.0` reports flip rate **4.76% vs Kev's 7.41%** because of it.

### 5. Calibrate — after training, on held-out data only

Two things, in this order:

1. **Temperature per (question type, option count) bucket** — Laya already ships this; we ported it.
2. **The correctness head on out-of-fold predictions** — **we built this today** (`bench/correctness_head.py`).
   It predicts "am I right" from the *shape* of the prediction and never sees the gold label.

**These are what turn a raw model into one whose probabilities can be trusted.**

### 6. The anti-leak discipline — the part that decides whether the number is real

`verdict-2.0` is most careful here and we should copy it exactly:

- partition at the **case-id level**, not the question level — sibling questions from one case must
  never straddle a fold
- **fit / calib / dev** split (theirs: 4,380 / 820 / 800 decisions)
- hyperparameters and checkpoint selection use **dev only**
- temperature and the correctness head are fit on **calib only**
- the **test split is read exactly once**, after everything is frozen, behind an explicit confirm gate
- verify **zero case-id overlap** and **zero duplicate state payloads** between train and test

**Without this, a good number means nothing** — and we'd be the people publishing a fabricated win rate.

### 7. Train

Reference: 8.8 h wall clock, 8 epochs, best checkpoint at epoch 6, ~5.8 GB peak on a 6 GB card.
**Our M4 has 16 GB unified**, so memory is not the constraint it was for them. Expect it slower per
step than a 1660 Ti in raw FLOPs, but with far more headroom — gradient checkpointing should be
unnecessary at Base.

### 8. Export to the ANE — our existing pipeline, unchanged

`bench/export_laya_ane.py`'s gate → `coreai-build compile --preferred-compute neural-engine` →
`bench/aot_verify.sh` → `bench/latency_protocol.py` → the JevBench adapter.

**All of that is already built and proven.** The model just drops in.

---

## What we'd have at the end

| | |
| --- | --- |
| a **150M decision model we trained**, Apache-2.0 base, on public Apache-2.0 data | |
| running on the **ANE at ~26 ms/decision** | vs their **40 ms on a desktop GPU** |
| with a **measured** calibration and a correctness channel | |
| and a **reproducible** pipeline: data → train → export → benchmark | |

**That is the whole loop, ours, end to end.**

---

## The honest risks

1. **8.8 hours was their number on their data.** Ours may not converge to the same place, and a
   failed training run is a real outcome, not a bug.
2. **The correctness head we measured was fit on 231 items.** On 4,380 it should be better — but that
   is an expectation, not a measurement.
3. **`answerdotai/ModernBERT-base` returned 401** when I checked it — gated or renamed. mmBERT-base is
   already local and already ported, so we are not blocked, but the base choice needs confirming.
4. **Time Machine is still broken and has never completed a backup.** Training will write multi-GB
   checkpoints. That is the one environment risk worth fixing *before* we start, not because we need
   the room, but because a corrupt write is exactly what cost us the Von investigation.
