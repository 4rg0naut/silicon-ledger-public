#!/usr/bin/env python3
"""Test our groundedness winner against WiCE.

We hand-labelled 55 items. That was too few to conclude anything. WiCE gives 958 claims with ~3
evidence chunks each, human-annotated, in our verdict space.

TWO THINGS THIS MUST GET RIGHT, both from WiCE's own documentation:

1. **Maximum over chunks.** The same claim appears ~3 times with different evidence chunks, because
   different annotators selected different supporting sentences. The published protocol is to take
   the maximum entailment score over all chunks for each claim. Evaluating per-row instead would
   understate every model and would not be comparable to any published number.

2. **`not_supported` is not `contradicted`.** WiCE measures entailment. A claim can fail to be
   supported because the source contradicts it OR because the source is silent. So the honest
   primary metric is binary: is the claim supported AT ALL.

     gold  has support  = supported + partially_supported
     model has support  = entailment
"""

from __future__ import annotations

import json
import collections
from pathlib import Path

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

WICE = Path("/Volumes/data/local_ai_stack/data/wice/oracle_subclaim_test.jsonl")
DEV = "mps" if torch.backends.mps.is_available() else "cpu"
MAP = {0: "entailment", 1: "neutral", 2: "contradiction"}


def main():
    rows = [json.loads(l) for l in open(WICE) if l.strip()]
    by_id = collections.defaultdict(list)
    for r in rows:
        by_id[r["meta"]["id"]].append(r)
    claims = sorted(by_id)
    print(f"  claims {len(claims)}   chunks {len(rows)}   device {DEV}")

    tok = AutoTokenizer.from_pretrained("models/von-1.0")
    model = AutoModelForSequenceClassification.from_pretrained("models/von-1.0").to(DEV).eval()

    results = []
    done = 0
    for cid in claims:
        chunks = by_id[cid]
        golds = {c["label"] for c in chunks}
        gold = chunks[0]["label"]
        assert len(golds) == 1, f"{cid} has inconsistent labels {golds}"
        best = None
        for c in chunks:
            passage = "\n".join(c["evidence"])
            enc = tok(passage, c["claim"], truncation="only_first", max_length=2048,
                      return_tensors="pt")
            enc = {k: v.to(DEV) for k, v in enc.items()}
            with torch.no_grad():
                p = model(**enc).logits.softmax(-1).cpu()[0]
            rec = {"id": cid, "gold": gold,
                   "p_ent": float(p[0]), "p_neu": float(p[1]), "p_con": float(p[2]),
                   "pred": MAP[int(p.argmax())], "conf": float(p.max())}
            # MAX over chunks on entailment probability -- the published protocol
            if best is None or rec["p_ent"] > best["p_ent"]:
                best = rec
        results.append(best)
        done += 1
        if done % 200 == 0:
            print(f"    {done}/{len(claims)} ...", flush=True)

    gold_dist = collections.Counter(r["gold"] for r in results)
    print(f"\n  per-claim gold: {dict(gold_dist)}")

    # --- primary metric: is the claim supported at all? -------------------------------
    GOLD_SUP = {"supported", "partially_supported"}
    tp = tn = fp = fn = 0
    for r in results:
        g = r["gold"] in GOLD_SUP
        p = r["pred"] == "entailment"
        if g and p: tp += 1
        elif g and not p: fn += 1
        elif not g and p: fp += 1
        else: tn += 1
    n = len(results)
    acc = (tp + tn) / n
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    print(f"\n  === PRIMARY: supported-at-all (binary), max-over-chunks ===")
    print(f"    accuracy {acc:.3f}   precision {prec:.3f}   recall {rec:.3f}   F1 {f1:.3f}")
    print(f"    confusion  TP {tp}  FN {fn}  FP {fp}  TN {tn}")

    # --- per gold class -----------------------------------------------------------------
    print(f"\n  === per gold label ===")
    for lab in ("supported", "partially_supported", "not_supported"):
        sub = [r for r in results if r["gold"] == lab]
        if not sub:
            continue
        preds = collections.Counter(r["pred"] for r in sub)
        ent = preds["entailment"] / len(sub)
        print(f"    {lab:20} n={len(sub):4}  says-entailment {ent:5.1%}   "
              f"[ent {preds['entailment']}, neu {preds['neutral']}, con {preds['contradiction']}]")

    # --- calibration --------------------------------------------------------------------
    print(f"\n  === does confidence track correctness? ===")
    for lo, hi in [(0, 0.5), (0.5, 0.8), (0.8, 0.95), (0.95, 1.01)]:
        sub = [r for r in results if lo <= r["conf"] < hi]
        if sub:
            ok = sum(1 for r in sub if (r["gold"] in GOLD_SUP) == (r["pred"] == "entailment"))
            print(f"    conf {lo:.2f}-{hi:.2f}  n={len(sub):4}  accuracy {ok/len(sub):.3f}")

    out = Path(__file__).resolve().parent / "wice_von_results.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\n  wrote {out}")


if __name__ == "__main__":
    main()