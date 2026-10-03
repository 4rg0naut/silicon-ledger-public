# Morning brief — what ran overnight, and what to do with it

## The run

**`train-decision`** — detached, started 2026-09-22, ~2.2 h ETA.

```
bench/train_decision_model.py --epochs 8 --batch 4 --max-len 256
hub logs train-decision        # live
work/training/best.pt          # best by dev loss
work/training/last.pt          # latest
```

**First 300 steps:** loss **3.52 → ~1.35**, steady **0.83 s/step**, no stalls.

## What was trained

| | |
| --- | --- |
| base | **ModernBERT-base** (~150M), apache-2.0 |
| head | **Laya's marker-pointer** — every option scored in one pass |
| data | `LocalLLaMA/typed-decisions`, 1,200 cases |
| split | **case-id level** — 960 fit / 180 calib; sibling questions cannot straddle folds |
| loss | soft CE + Brier |
| **test split** | **never read** — reserved for one gated evaluation |

## What to read in the morning

**Judge from epoch 2 onward.** The epoch-0 dev accuracy prints after only 20 steps and is meaningless.

Look for: **dev accuracy rising, dev loss falling**, and `best.pt` being overwritten.

## Then, in order

1. **Check the dev curve** — if accuracy is still climbing at epoch 8, more epochs would help.
2. **Run 2 with the two missing losses.** `bench/losses.py` is written and **unit-tested**: RPS for
   ordinal questions, Permutation-KL for option-order sensitivity. Both pass. Run 1 omitted them
   deliberately — untested code in an unattended job loses the night.
3. **Calibrate** — temperature per (question type, option count), then the correctness head
   (`bench/correctness_head.py`, −69% ECE measured).
4. **Export to the ANE** — `export_laya_ane.py` → `coreai-build` → `aot_verify.sh` →
   `latency_protocol.py` → the JevBench adapter. **All of it already built and proven; the model
   just drops in.**

## Two things I would not claim

- **This will not beat Laya on run 1.** `verdict-2.0` needed 8.8 h on a 1660 Ti with three losses and
  dual calibration to reach 77.1%. Run 1 is the loop working, not the result.
- **The dev numbers are on 180 held-out cases, not the 400-case test split.** Small. Treat the shape
  of the curve as informative and the absolute value as provisional.

## The one environment risk

**Time Machine has never completed a backup** (`Failed to mount destination`). The run writes 655 MB
checkpoints to a drive with no working backup. Not blocking — but a corrupt write is exactly what cost
us the Von investigation, and it would be cheap to fix.
