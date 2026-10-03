#!/usr/bin/env python3
"""Summarise an ane-probe scan CSV: overall ANE coverage + notable ops.

Usage: python3 analyze_ane_scan.py <csv>
"""
import csv
import sys
from collections import Counter


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else (
        "repos/ane-probe/results/M4/macOS_27.0/coremltools_v9.0/ane_support_results.csv"
    )
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        print("empty csv")
        return 1

    print(f"file    : {path}")
    print(f"columns : {list(rows[0].keys())}")
    print(f"rows    : {len(rows)}")

    status = Counter((r.get("status") or "?").strip() for r in rows)
    print(f"status  : {dict(status)}")

    ok = [r for r in rows if (r.get("status") or "").strip() == "ok"]

    def has_ane(r: dict) -> bool:
        return "ANE" in (r.get("supported") or "")

    ane_yes = [r for r in ok if has_ane(r)]
    ane_no = [r for r in ok if not has_ane(r)]
    print(f"ok rows : {len(ok)}   ANE-supported: {len(ane_yes)}   not-ANE: {len(ane_no)}")
    if ok:
        print(f"ANE rate: {100.0 * len(ane_yes) / len(ok):.1f}% of ok ops")

    print("\n--- ops NOT supported on ANE (with reason) ---")
    for r in sorted(ane_no, key=lambda x: (x.get("op_name") or "")):
        name = (r.get("op_name") or "?").strip()
        reason = (r.get("reason") or "").strip()
        print(f"  {name:<20} {reason[:90]}")

    print("\n--- transformer / embedding-relevant ops ---")
    watch = [
        "matmul", "linear", "conv", "add", "mul", "sub", "softmax", "gelu", "relu",
        "layer_norm", "layernorm", "gather", "embedding", "transpose", "reshape",
        "concat", "slice", "reduce_mean", "exp", "erf", "rsqrt", "pow",
    ]
    by_op = {}
    for r in rows:
        op = (r.get("op_name") or "").strip().lower()
        by_op.setdefault(op, []).append(r)
    for w in watch:
        hits = [r for op, rs in by_op.items() if op == w for r in rs]
        if not hits:
            continue
        r = hits[0]
        st = (r.get("status") or "?").strip()
        sup = (r.get("supported") or "-").strip()
        pref = (r.get("preferred") or "-").strip()
        flag = "YES" if has_ane(r) else "no "
        print(f"  {w:<12} status={st:<6} ANE={flag}  supported=[{sup}]  preferred={pref}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
