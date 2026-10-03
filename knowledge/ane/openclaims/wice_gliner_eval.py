#!/usr/bin/env python3
"""Evaluate GLiNER2.5-Decide on WiCE, against the same protocol Von was measured on.

Same task, same 958 claims, same max-over-chunks rule, so the two are directly comparable.

Two things about this model shape the harness:

1. **The published protocol is "maximum entailment score over all chunks".** Von returns a clean
   entailment probability, so that was a max over numbers. GLiNER2.5-Decide returns a LABEL plus the
   confidence of whichever label won -- so if a chunk's argmax is `not_supported` we do not get
   P(supported). We therefore take the max in LABEL space: a claim counts as supported if ANY of its
   chunks classifies as `supported`. That is the faithful analogue, and it is stated rather than
   glossed.

2. **The model takes text + a schema of typed questions, not a premise/hypothesis pair.** So the
   claim and the passage are combined into one text under explicit headings. This is the natural
   framing for a non-generative classifier and it is the one the model card demonstrates.

Runs on CPU deliberately: measured on this machine, batched CPU is 49 ms/item against 291 ms on MPS.
For a 435M encoder the GPU loses to the CPU.

usage: .venv/bin/python wice_gliner_eval.py
"""
from __future__ import annotations

import json
import collections
from pathlib import Path

import time

WICE = Path("/Volumes/data/local_ai_stack/data/wice/oracle_subclaim_test.jsonl")
OUT = Path(__file__).resolve().parent / "wice_gliner_results.json"

TASK = {"support": ["supported", "partially_supported", "not_supported"]}


def frame(claim: str, passage: str) -> str:
    return f"CLAIM:\n{claim}\n\nSOURCE PASSAGE:\n{passage}"


def main():
    rows = [json.loads(l) for l in open(WICE) if l.strip()]
    print(f"  rows {len(rows)}   claims {len({r['meta']['id'] for r in rows})}")

    from gliner2 import AutoExtractor
    m = AutoExtractor.from_pretrained("fastino/GLiNER2.5-Decide")

    texts = [frame(r["claim"], "\n".join(r["evidence"])) for r in rows]
    t0 = time.perf_counter()
    out = m.batch_classify_text(texts, TASK, batch_size=8, include_confidence=True)
    el = time.perf_counter() - t0
    print(f"  classified {len(texts)} in {el:.0f}s  ({el/len(texts)*1000:.0f} ms/item)")

    # group by claim and take the max over chunks in label space
    by_claim = collections.defaultdict(list)
    for r, o in zip(rows, out):
        spec = o.get("support", {})
        lab = spec.get("label") if isinstance(spec, dict) else spec
        conf = spec.get("confidence", 0.0) if isinstance(spec, dict) else 0.0
        by_claim[r["meta"]["id"]].append({"gold": r["label"], "pred": lab, "conf": conf})

    results = []
    for cid, chunks in by_claim.items():
        gold = chunks[0]["gold"]
        sup = [c for c in chunks if c["pred"] == "supported"]
        part = [c for c in chunks if c["pred"] == "partially_supported"]
        if sup:
            pred, conf = "supported", max(c["conf"] for c in sup)
        elif part:
            pred, conf = "partially_supported", max(c["conf"] for c in part)
        else:
            pred, conf = "not_supported", max(c["conf"] for c in chunks)
        results.append({"id": cid, "gold": gold, "pred": pred, "conf": conf,
                        "n_chunks": len(chunks)})

    gold_dist = collections.Counter(r["gold"] for r in results)
    pred_dist = collections.Counter(r["pred"] for r in results)
    print(f"\n  per-claim gold     : {dict(gold_dist)}")
    print(f"  per-claim predicted: {dict(pred_dist)}")

    GOLD_SUP = {"supported", "partially_supported"}
    tp = tn = fp = fn = 0
    for r in results:
        g = r["gold"] in GOLD_SUP
        p = r["pred"] in GOLD_SUP
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

    print(f"\n  === per gold label ===")
    for lab in ("supported", "partially_supported", "not_supported"):
        sub = [r for r in results if r["gold"] == lab]
        if not sub: continue
        c = collections.Counter(r["pred"] for r in sub)
        print(f"    {lab:20} n={len(sub):4}  says-supported {(c['supported']+c['partially_supported'])/len(sub):5.1%}"
              f"   [sup {c['supported']}, part {c['partially_supported']}, not {c['not_supported']}]")

    print(f"\n  === does confidence track correctness? ===")
    for lo, hi in [(0, 0.5), (0.5, 0.8), (0.8, 0.95), (0.95, 1.01)]:
        sub = [r for r in results if lo <= r["conf"] < hi]
        if sub:
            ok = sum(1 for r in sub if (r["gold"] in GOLD_SUP) == (r["pred"] in GOLD_SUP))
            print(f"    conf {lo:.2f}-{hi:.2f}  n={len(sub):4}  accuracy {ok/len(sub):.3f}")

    OUT.write_text(json.dumps(results, indent=2))
    print(f"\n  wrote {OUT}")


if __name__ == "__main__":
    main()