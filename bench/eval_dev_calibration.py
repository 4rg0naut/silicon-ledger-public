#!/usr/bin/env python3
"""Evaluate the trained decision checkpoints on the dev (calib) split.

Computes, per checkpoint: argmax accuracy, Brier, CE, ECE, and mean confidence --
and the same split by annotator disagreement (label_agreement.total_variation).

Reads only the dev split. The test split is deliberately untouched.

usage: python bench/eval_dev_calibration.py
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))

from train_decision_model import (  # noqa: E402
    DATA, BASE, build_items, collate, load_rows, DecisionModel,
)
from transformers import AutoTokenizer  # noqa: E402


def dev_split(rows: list[dict]) -> list[dict]:
    """Replicate the trainer's case-id-level split exactly (same seeds, same order)."""
    torch.manual_seed(0); random.seed(0); np.random.seed(0)
    ids = sorted({r["id"] for r in rows})
    random.shuffle(ids)
    n_fit, n_cal = int(len(ids) * 0.80), int(len(ids) * 0.15)
    cal_ids = set(ids[n_fit:n_fit + n_cal])
    return [r for r in rows if r["id"] in cal_ids], cal_ids


def tv_lookup(rows: list[dict]) -> dict:
    """(case_id, question) -> total_variation across annotators."""
    out = {}
    for r in rows:
        la = json.loads(r["label_agreement"]) if isinstance(r["label_agreement"], str) else r["label_agreement"]
        for q, spec in la.items():
            out[(r["id"], q)] = float(spec.get("total_variation", 0.0))
    return out


@torch.no_grad()
def evaluate(model, items, tok, dev, batch=4):
    """Return per-decision records: (correct, brier, ce, confidence, tv)."""
    recs = []
    for bi in range(0, len(items), batch):
        b = collate(items[bi:bi + batch], tok.pad_token_id or 0)
        b = {k: v.to(dev) for k, v in b.items()}
        lo = model(b["input_ids"], b["attention_mask"], b["selection"], b["qtype"])
        p = F.softmax(lo, dim=-1)
        for i, it in enumerate(items[bi:bi + batch]):
            k = len(it["target"])
            tgt = b["target"][i, :k].float()
            pi = p[i, :k]
            ti = tgt / tgt.sum().clamp_min(1e-9)
            recs.append({
                "case": it.get("id"),
                "q": it.get("qname"),
                "correct": int(int(pi.argmax()) == int(ti.argmax())),
                "brier": float(((pi - ti) ** 2).sum()),
                "ce": float(-(ti * torch.log(pi.clamp_min(1e-12))).sum()),
                "conf": float(pi.max()),
                "tv": it.get("tv", 0.0),
            })
    return recs


def summarize(name, recs):
    n = len(recs)
    acc = np.mean([r["correct"] for r in recs])
    brier = np.mean([r["brier"] for r in recs])
    ce = np.mean([r["ce"] for r in recs])
    conf = np.mean([r["conf"] for r in recs])
    # ECE over 10 confidence bins
    confs = np.array([r["conf"] for r in recs])
    correct = np.array([r["correct"] for r in recs], dtype=float)
    ece = 0.0
    for lo in np.linspace(0, 0.9, 10):
        m = (confs >= lo) & (confs < lo + 0.1)
        if m.sum():
            ece += (m.sum() / n) * abs(correct[m].mean() - confs[m].mean())
    print(f"\n  {name}")
    print(f"    acc {acc:.4f}   brier {brier:.4f}   ce {ce:.4f}")
    print(f"    mean confidence {conf:.4f}   ECE {ece:.4f}   gap {conf - acc:+.4f}")
    for lo, hi in [(0, .15), (.15, .3), (.3, .5), (.5, 1.01)]:
        m = [(r["tv"] >= lo and r["tv"] < hi) for r in recs]
        idx = np.array(m, dtype=bool)
        if idx.sum():
            a = np.mean([r["correct"] for r, k in zip(recs, m) if k])
            c = np.mean([r["conf"] for r, k in zip(recs, m) if k])
            print(f"      TV {lo:.2f}-{hi:.2f}: n={idx.sum():>4}  acc {a:.4f}  conf {c:.4f}  gap {c - a:+.4f}")
    return {"acc": acc, "brier": brier, "ce": ce, "ece": ece, "conf": conf}


def main():
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(BASE)
    rows = load_rows("train")
    cal, cal_ids = dev_split(rows)
    print(f"  dev cases {len(cal)}  device {dev}")

    tvs = tv_lookup(rows)
    items = build_items(cal, tok)
    for it in items:
        it["tv"] = tvs.get((it.get("id"), it.get("qname")), 0.0)
    print(f"  dev decisions {len(items)}")

    out = {}
    for ck in ["best.pt", "last.pt"]:
        p = ROOT / "work" / "training" / ck
        if not p.exists():
            print(f"  missing {ck}"); continue
        c = torch.load(p, map_location="cpu", weights_only=False)
        m = DecisionModel(BASE).to(dev)
        m.load_state_dict(c["model"])
        m.eval()
        recs = evaluate(m, items, tok, dev)
        s = summarize(f"{ck}  (epoch {c.get('epoch')})", recs)
        s["epoch"] = c.get("epoch")
        out[ck] = s
        del m
        if dev == "mps":
            torch.mps.empty_cache()

    print("\n  === verdict ===")
    if "best.pt" in out and "last.pt" in out:
        b, l = out["best.pt"], out["last.pt"]
        print(f"    accuracy : best {b['acc']:.4f}  vs last {l['acc']:.4f}  -> {'best' if b['acc']>l['acc'] else 'last'} wins")
        print(f"    brier    : best {b['brier']:.4f}  vs last {l['brier']:.4f}  -> {'best' if b['brier']<l['brier'] else 'last'} wins")
        print(f"    ECE      : best {b['ece']:.4f}  vs last {l['ece']:.4f}  -> {'best' if b['ece']<l['ece'] else 'last'} wins")
    (ROOT / "results" / "dev-calibration.json").write_text(json.dumps(out, indent=2))
    print(f"\n  wrote results/dev-calibration.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())