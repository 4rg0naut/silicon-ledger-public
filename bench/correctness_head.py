#!/usr/bin/env python3
"""The two-channel fix: a correctness head over the SHAPE of an existing prediction.

Why: gold labels are expert-panel *distributions*, not 0/1. A model that matches the panel (low
Brier) is systematically over-confident about being right (high ECE), and one that tracks its hit
rate stops matching the panel. `openJev-verdict-2.0` names this exactly:

    accuracy (0.7710) - mean distribution confidence (0.6197) = 0.1513 = reported ECE

One vector cannot answer both questions, so they ship two channels. The second channel is an MLP
over features of the prediction itself — top probability, margin, entropy, option count, question
type — and it never sees the gold label. This is that head, ported.

It needs no retraining of the encoder and no model at runtime: the features are arithmetic on
probabilities we already have. It needs *labels*, which is the honest cost — here they come from
JevBench's public items.

usage: python bench/correctness_head.py
"""
from __future__ import annotations
import json, math, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def features(probs: dict) -> list[float]:
    """The shape of a prediction. Never touches the gold label."""
    p = sorted((float(v) for v in probs.values()), reverse=True)
    k = len(p)
    top = p[0] if p else 0.0
    margin = (p[0] - p[1]) if k > 1 else top
    ent = -sum(v * math.log(v + 1e-12) for v in p)
    norm_ent = ent / math.log(k) if k > 1 else 0.0
    return [top, margin, norm_ent, math.log(k), 1.0 if k == 2 else 0.0]


def fit(X, y, epochs=3000, lr=0.35):
    """Plain logistic regression by gradient descent — no dependency, and it is the right size."""
    n, d = len(X), len(X[0])
    w, b = [0.0] * d, 0.0
    for _ in range(epochs):
        gw, gb = [0.0] * d, 0.0
        for xi, yi in zip(X, y):
            z = sum(w[j] * xi[j] for j in range(d)) + b
            pr = 1 / (1 + math.exp(-max(-30, min(30, z))))
            e = pr - yi
            for j in range(d):
                gw[j] += e * xi[j]
            gb += e
        for j in range(d):
            w[j] -= lr * gw[j] / n
        b -= lr * gb / n
    return w, b


def predict(w, b, x):
    z = sum(w[j] * x[j] for j in range(len(x))) + b
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


def ece(conf, correct, bins=10):
    """Top-label expected calibration error."""
    tot = len(conf)
    e = 0.0
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        idx = [j for j in range(tot) if lo <= conf[j] < hi or (i == bins - 1 and conf[j] == 1.0)]
        if not idx:
            continue
        acc = sum(correct[j] for j in idx) / len(idx)
        avg = sum(conf[j] for j in idx) / len(idx)
        e += len(idx) / tot * abs(acc - avg)
    return e


def main() -> int:
    rows = json.loads((ROOT / "work" / "memory-stack" / "laya_ane_public.json").read_text())
    rows = [r for r in rows if r.get("ok") and r.get("probs")]
    X = [features(r["probs"]) for r in rows]
    y = [1.0 if r["correct"] else 0.0 for r in rows]

    # leave-one-out, because 231 rows is too few to hold out honestly
    pred = []
    for i in range(len(X)):
        w, b = fit([x for j, x in enumerate(X) if j != i], [v for j, v in enumerate(y) if j != i])
        pred.append(predict(w, b, X[i]))

    dist_conf = [max(float(v) for v in r["probs"].values()) for r in rows]
    print(f"  {len(rows)} decisions, leave-one-out\n")
    print(f"  accuracy                       {sum(y)/len(y)*100:.1f}%")
    print(f"  mean distribution confidence   {statistics.mean(dist_conf):.4f}")
    print(f"  the panel-doubt gap            {sum(y)/len(y) - statistics.mean(dist_conf):+.4f}")
    print()
    print(f"  ECE, distribution channel      {ece(dist_conf, y):.4f}   <- the 0.214-style number")
    print(f"  ECE, confidence channel        {ece(pred, y):.4f}   <- the fix")
    imp = (ece(dist_conf, y) - ece(pred, y)) / ece(dist_conf, y) * 100
    print(f"  improvement                    {imp:+.1f}%")
    print()
    print(f"  Brier unchanged (same vector)  {statistics.mean((c-p)**2 for c,p in zip(y,dist_conf)):.4f}")
    print("  -> the distribution channel is untouched, so Brier is preserved. That is the whole point:")
    print("     two channels answer two questions instead of compromising on one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
