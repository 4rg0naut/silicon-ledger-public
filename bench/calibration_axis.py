#!/usr/bin/env python3
"""Measure JevBench's Calibration axis with and without the correctness head.

JevBench's Calibration is the mean of two sub-axes (its own `composite_v13.calibration`):
  (a) 100 * (1 - ECE / 0.5)                     -- top-label expected calibration error
  (b) 100 * (1 - mean total-variation distance)  -- fidelity to the exact gold distribution

The correctness head changes (a) and leaves (b) untouched: it re-reads the SAME probability vector,
it does not reshape it. That is the point of two channels, and this measures it rather than projecting.

usage: python bench/calibration_axis.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
sys.path.insert(0, str(ROOT / "work" / "jevbench"))
from correctness_head import features, fit, predict, ece          # noqa: E402
from jevbench.composite_v13 import calibration as jev_calibration  # noqa: E402


def main() -> int:
    rows = [r for r in json.loads((ROOT / "work" / "memory-stack" / "laya_ane_public.json").read_text())
            if r.get("ok") and r.get("probs")]
    X = [features(r["probs"]) for r in rows]
    y = [1.0 if r["correct"] else 0.0 for r in rows]

    # leave-one-out: the head never scores a decision it was fit on
    conf = []
    for i in range(len(X)):
        w, b = fit([x for j, x in enumerate(X) if j != i], [v for j, v in enumerate(y) if j != i])
        conf.append(predict(w, b, X[i]))

    dist_conf = [max(float(v) for v in r["probs"].values()) for r in rows]
    e_dist, e_conf = ece(dist_conf, y), ece(conf, y)

    # sub-axis (b) needs the gold distributions, which live in JevBench's `probability` family.
    # Those items are in the public set; total-variation distance is computed against `gold_probs`.
    gold = []
    for line in (ROOT / "work" / "jevbench" / "datasets" / "public" / "hard.jsonl").read_text().splitlines():
        if line.strip():
            d = json.loads(line)
            if d.get("provenance", {}).get("gold_probs"):
                gold.append(d)
    print(f"  {len(rows)} decisions | {len(gold)} probability items with gold distributions")
    print()
    print(f"  {'':<26}{'ECE':>9}{'sub-axis (a)':>15}{'sub-axis (b)':>15}{'Calibration':>13}")
    for label, e in (("distribution channel", e_dist), ("+ correctness head", e_conf)):
        a = max(0.0, 100 * (1 - e / 0.5))
        print(f"  {label:<26}{e:>9.4f}{a:>15.1f}{'n/a (unchanged)':>15}{'—':>13}")
    print()
    print(f"  JevBench's own calibration() with ECE only: "
          f"{jev_calibration(e_dist):.1f} -> {jev_calibration(e_conf):.1f}")
    print(f"  (fidelity sub-axis not computable here: our runs did not emit distributions for the")
    print(f"   {len(gold)} probability items, so (b) is held equal across both rows.)")
    print()
    print(f"  => the gain is entirely in (a): {max(0.0,100*(1-e_dist/0.5)):.1f} -> "
          f"{max(0.0,100*(1-e_conf/0.5)):.1f}, i.e. "
          f"{(max(0.0,100*(1-e_conf/0.5))-max(0.0,100*(1-e_dist/0.5)))/2:+.1f} on the mean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
