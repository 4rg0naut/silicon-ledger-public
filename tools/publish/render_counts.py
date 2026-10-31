#!/usr/bin/env python3
"""render_counts.py — fill front-door counts from results/COUNTS.json via marker comments.

A marker is `<!-- gen:KEY -->value<!-- /gen -->`. Sources keep the markers; the value between them is
rewritten from COUNTS.json. In the staging tree the markers are stripped (only the value remains), so
numbers inside bold text, URLs or badges stay valid markdown. An unknown KEY is an error.

modes:
  --write        rewrite values in the tracked sources (private README + public overlay files)
  --check        exit 1 if any source value differs from COUNTS.json (writes nothing)
  --stage DIR    render a staging tree: strip markers everywhere under DIR (publish.sh calls this)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COUNTS = ROOT / "results" / "COUNTS.json"
OVERLAY = ROOT / "tools" / "publish" / "public-content"
TARGETS = [ROOT / "README.md"] + sorted(OVERLAY.glob("*.md"))
MARK = re.compile(r"<!-- gen:(\w+) -->(.*?)<!-- /gen -->", re.S)


def values(c: dict) -> dict[str, str]:
    n, x = c["measurements"], c["experiments"]
    return {
        "measurements": str(n),
        "experiments": str(x),
        "experiment_range": c["experiment_range"],
        "claims_emitted": str(c["claims_emitted"]),
        "claims_verified": str(c["claims_verified"]),
        "claims_disputed": str(c["claims_disputed"]),
        "spine_events": str(c["spine_events"]),
        "machines_phrase": c["machines_phrase"],
        "machines_list": c["machines_list"],
        "badge_measurements": f"[![measurements](https://img.shields.io/badge/measurements-{n}-blue)](results/measurements.json)",
        "badge_experiments": f"[![experiments](https://img.shields.io/badge/experiments-{x}-blue)](PUBLIC-INDEX.md)",
    }


def fill(text: str, vals: dict[str, str], keep: bool) -> tuple[str, list[str]]:
    errs = []

    def sub(m):
        k = m.group(1)
        if k not in vals:
            errs.append(f"unknown gen key {k!r}")
            return m.group(0)
        return f"<!-- gen:{k} -->{vals[k]}<!-- /gen -->" if keep else vals[k]

    return MARK.sub(sub, text), errs


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--stage")
    a = ap.parse_args()
    vals = values(json.loads(COUNTS.read_text()))

    if a.stage:
        stage = Path(a.stage)
        bad = []
        for p in sorted(stage.rglob("*.md")):
            rel = p.relative_to(stage)
            if rel.parts[:2] == ("tools", "publish") or "raw" in rel.parts:
                continue
            t = p.read_text(errors="replace")
            if "<!-- gen:" not in t:
                continue
            new, errs = fill(t, vals, keep=False)
            bad += [f"{rel}: {e}" for e in errs]
            p.write_text(new)
        left = [str(p.relative_to(stage)) for p in stage.rglob("*.md")
                if "<!-- gen:" in p.read_text(errors="replace") and p.relative_to(stage).parts[:2] != ("tools", "publish")
                and "raw" not in p.relative_to(stage).parts]
        bad += [f"{p}: gen marker left in staging" for p in left]
        for b in bad:
            print("render_counts:", b, file=sys.stderr)
        print(f"render_counts: staging rendered ({len(bad)} problems)")
        return 1 if bad else 0

    drift, errs_all = [], []
    for p in TARGETS:
        t = p.read_text()
        new, errs = fill(t, vals, keep=True)
        errs_all += [f"{p.relative_to(ROOT)}: {e}" for e in errs]
        if new != t:
            drift.append(p)
            if a.write:
                p.write_text(new)
    for e in errs_all:
        print("render_counts:", e, file=sys.stderr)
    if a.write:
        print(f"render_counts: {len(drift)} file(s) updated: {[str(p.relative_to(ROOT)) for p in drift]}")
        return 1 if errs_all else 0
    for p in drift:
        print(f"render_counts: stale values in {p.relative_to(ROOT)}")
    return 1 if (drift or errs_all) else 0


if __name__ == "__main__":
    sys.exit(main())
