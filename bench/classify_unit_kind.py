#!/usr/bin/env python3
"""Ask Laya, on the ANE, to classify a measurement's `unit` into a closed set of kinds.

This is the task reshaped as a **typed decision** instead of as text generation:

    state     = the row's descriptive unit string, verbatim
    question  = "Which quantity kind does this unit measure?"
    criteria  = the closed set of kinds (<= Laya's 32 option slots)
    answer    = a probability per kind

No JSON is emitted, nothing is written, and the model never produces prose. Ground truth is the
deterministic `unit_kind` already in measurements.json, so agreement is measurable.

usage: python bench/classify_unit_kind.py --bundle <path> --limit 40
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench")); sys.path.insert(0, str(ROOT / "work" / "jevbench"))

KINDS = ["ms", "s", "mw", "mj", "ndcg", "recall", "accuracy", "probability", "score", "cosine",
         "regions", "error", "delta", "ratio", "tokens", "bytes", "intervals", "count",
         "points", "items", "elements", "emb/s", "rows", "ops"]
CRIT = {
    "ms": "a duration in milliseconds", "s": "a duration in seconds",
    "mw": "power in milliwatts", "mj": "energy in millijoules",
    "ndcg": "a retrieval quality score (ndcg)", "recall": "a recall percentage",
    "accuracy": "an accuracy percentage", "probability": "a probability between 0 and 1",
    "score": "a score on some scale", "cosine": "a cosine similarity",
    "regions": "a count of neural-engine regions", "error": "an error or difference",
    "delta": "a change relative to a baseline", "ratio": "a ratio or speedup factor",
    "tokens": "a count of tokens", "bytes": "a size in bytes",
    "intervals": "a count of hardware intervals", "count": "a plain count",
    "points": "points on a 0-100 scale", "items": "a count of items",
    "elements": "a count of array elements", "emb/s": "embeddings per second",
    "rows": "a count of rows", "ops": "a count of operations",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--seq-len", type=int, default=256)
    args = ap.parse_args()

    import asyncio, threading
    from coreai.runtime import AIModel, NDArray, ComputeUnitKind, SpecializationOptions
    import importlib.util
    spec = importlib.util.spec_from_file_location("ja", ROOT / "bench" / "jevbench_ane.py")
    ja = importlib.util.module_from_spec(spec); spec.loader.exec_module(ja)

    rows = [r for r in json.loads((ROOT / "results" / "measurements.json").read_text())["measurements"]
            if r.get("unit_kind") in KINDS]
    # sample across kinds so the task is not dominated by one class
    by = {}
    for r in rows:
        by.setdefault(r["unit_kind"], []).append(r)
    sample = []
    for k, v in by.items():
        sample.extend(v[: max(1, args.limit // len(by) + 1)])
    sample = sample[: args.limit]

    ad = ja.LayaANEAdapter(args.bundle, seq_len=args.seq_len,
                           model_dir=ROOT / "models" / "laya-english", max_len=args.seq_len)
    ad.load()
    print(f"  Laya on the ANE | {len(KINDS)} kinds | {len(sample)} rows\n")

    agree = 0
    lat = []
    for r in sample:
        state = f"unit string: {r['unit']!r}\nmetric: {r.get('metric')!r}"
        import types
        task = types.SimpleNamespace(
            state=state, labels=KINDS,
            question={"type": "choice", "instructions": "Which quantity kind does this unit measure?",
                      "criteria": {k: CRIT[k] for k in KINDS}})
        res = ad.run(task)
        if not res.ok:
            print("  FAIL", res.error); continue
        pred = max(res.probs, key=res.probs.get)
        hit = pred == r["unit_kind"]
        agree += hit
        lat.append(res.latency_s)
        if not hit:
            print(f"    MISS  unit={r['unit'][:44]!r:<48} gold={r['unit_kind']:<10} got={pred}")
    lat.sort()
    n = len(lat)
    print(f"\n  agreement with the deterministic rule: {agree}/{n} = {agree/max(1,n)*100:.1f}%")
    print(f"  p50 {lat[len(lat)//2]*1000:.0f} ms per decision")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
