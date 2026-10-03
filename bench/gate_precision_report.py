#!/usr/bin/env python3
"""Run the zoo's full numerical + RETRIEVAL gate on real runtime embeddings.

Cosine alone does not answer "is the fp16 build usable?". For an embedder the question is
whether retrieval survives: exact top-1 per query, score error within 0.01, and no inversion
of any document pair the fp32 oracle separates by >= 0.001. That is what `_gate_metrics.py`
(shared by every zoo stage) measures, and it is the standard the published bundle was held to.

Inputs are embeddings dumped from the actual Core AI runtime by
`granite-runner --dump-embeddings`, not from the torch graph.

usage: .venv/bin/python bench/gate_precision_report.py work/gate/fp32.json work/gate/fp16_v3.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "repos" / "coreai-model-zoo" / "conversion" / "granite_embedding"))

from _gate_metrics import (COSINE_MIN, MAX_ABS, NORM_ERROR_MAX,  # noqa: E402
                           SIMILARITY_ERROR_MAX, gate_vectors)

GOLDEN = ROOT / "work" / "granite-embedding-97m" / "fixtures" / "golden_s128.json"


def report(label: str, vectors: dict) -> dict:
    golden = json.loads(GOLDEN.read_text())
    g = gate_vectors(golden, vectors)

    norms = [m.get("norm_error", 0) for m in g["per_fixture"].values()]
    print(f"\n=== {label} ===")
    print(f"  status        : {g['status']}")
    print(f"  min cosine    : {g['min_cosine']:.9f}   (threshold >= {COSINE_MIN})")
    print(f"  max |err|     : {g['max_abs']:.3e}   (threshold <= {MAX_ABS})")
    print(f"  max norm err  : {max(norms):.3e}   (threshold <= {NORM_ERROR_MAX})")

    print(f"  retrieval     : {len(g['retrieval'])} queries")
    flips = 0
    worst = 0.0
    for r in g["retrieval"]:
        flips += r["clear_pair_flips"]
        worst = max(worst, r["max_score_error"])
        mark = "ok " if r["top1_match"] else "MISS"
        print(f"    {mark} {r['query']:<28} top1={r['top1_match']}  "
              f"score_err={r['max_score_error']:.2e}  margin={r['candidate_margin']:.4f}  "
              f"clear_pair_flips={r['clear_pair_flips']}")
    print(f"  clear pair flips (total) : {flips}   (threshold: 0)")
    print(f"  worst score error        : {worst:.3e}   (threshold <= {SIMILARITY_ERROR_MAX})")
    if g["failures"]:
        print(f"  FAILURES: {g['failures'][:8]}")

    return {"label": label, "status": g["status"], "min_cosine": g["min_cosine"],
            "max_abs": g["max_abs"], "max_norm_error": max(norms),
            "top1_all": all(r["top1_match"] for r in g["retrieval"]),
            "clear_pair_flips": flips, "worst_score_error": worst,
            "failures": g["failures"]}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    out = []
    for path in sys.argv[1:]:
        p = Path(path)
        out.append(report(p.stem, json.loads(p.read_text())))

    print("\n" + "=" * 92)
    print("RUNTIME EMBEDDING GATE — the zoo's own criteria, on the shipped artifacts")
    print("=" * 92)
    print(f"{'variant':<16}{'status':>7}{'min cosine':>16}{'max |err|':>12}"
          f"{'norm err':>11}{'top1 all':>10}{'flips':>7}{'score err':>12}")
    for r in out:
        print(f"{r['label']:<16}{r['status']:>7}{r['min_cosine']:>16.9f}{r['max_abs']:>12.2e}"
              f"{r['max_norm_error']:>11.2e}{str(r['top1_all']):>10}{r['clear_pair_flips']:>7}"
              f"{r['worst_score_error']:>12.2e}")

    dest = ROOT / "work" / "gate" / "report.json"
    dest.write_text(json.dumps(out, indent=2))
    print(f"\nrecord: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
