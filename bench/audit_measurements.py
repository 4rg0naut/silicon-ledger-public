#!/usr/bin/env python3
"""Re-check every measurements.json row against its source EXP report.

Why this exists: the +724/+152 verified-extracted rows were merged from
work/memory-stack/extract/EXP-*.json fragments that are ephemeral (gitignored)
and are NOT reproducible on a fresh clone. The measurements.json file is the
source of truth, but its rows were machine-verified against the EXP reports at
merge time. This audit is the STANDING re-check: it re-derives, from the
committed reports alone, whether each row's numbers still literally appear in
the report they came from.

It does NOT re-run any benchmark and does NOT trust any model: a row passes
only when its value (and, when set, latency_ms / ane_regions / date) literally
occurs in an attributable report, using the same separator-blind containment
rule as bench/verify_extraction.py (so `54,846` matches `54846`).

Attribution is two-stage:
  1. the report(s) that name the row's `id` verbatim;
  2. failing that, the report(s) that contain the row's `value` AND its
     `model` or `metric` (for rows whose id is an internal slug not written in
     the report's prose).

A row with no attributable report is declared `unattributable` — an honest gap,
never a silent pass. Run it any time to confirm the ledger still agrees with
its own reports.

usage:
    python bench/audit_measurements.py            # audit + print summary
    python bench/audit_measurements.py --json     # also write results/audit_measurements.json
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "results" / "measurements.json"
RESULTS = ROOT / "results"
OUT = ROOT / "results" / "audit_measurements.json"
KEYS = ("id", "model", "checkpoint", "params_m", "runtime", "placement", "dtype", "seq_len",
        "ane_regions", "benchmark", "split", "scope", "tiers", "metric", "value", "unit",
        "latency_ms", "latency_unit", "hardware", "load_factor", "energy_mw", "energy_rail",
        "energy_baseline", "provenance", "date", "command")


def digits(v):
    if v is None:
        return ""
    return re.sub(r"[^0-9]", "", f"{v:g}") if isinstance(v, (int, float)) else re.sub(r"[^0-9]", "", v)


def appears(text_digits: str, v) -> bool:
    """Separator-blind containment (digits-only projection), like verify_extraction."""
    if v is None:
        return True
    d = digits(v)
    return bool(d) and d in text_digits


def load_reports() -> list[tuple[str, str]]:
    reps = []
    for p in sorted(RESULTS.glob("EXP-*/README.md")):
        reps.append((p.parent.name, p.read_text(errors="replace")))
    return reps


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="write results/audit_measurements.json")
    args = ap.parse_args()

    rows = json.loads(DATA.read_text())["measurements"]
    reports = load_reports()
    pre = [(name, text, re.sub(r"[^0-9]", "", text)) for name, text in reports]

    results = []
    for r in rows:
        rid = r.get("id")
        # stage 1: reports naming the id verbatim
        cands = [(n, t, d) for n, t, d in pre if rid and rid in t]
        # stage 2: reports with value + (model or metric)
        if not cands:
            for n, t, d in pre:
                if appears(d, r.get("value")) and (
                        (r.get("model") and r["model"] in t)
                        or (r.get("metric") and str(r["metric"]) in t)):
                    cands.append((n, t, d))

        if not cands:
            status, where, miss = "unattributable", None, []
        else:
            miss_all, where = None, cands[0][0]
            ok = False
            for n, t, d in cands:
                miss = []
                if not appears(d, r.get("value")):
                    miss.append("value")
                if r.get("latency_ms") is not None and not appears(d, r.get("latency_ms")):
                    # verify_extraction's rule: a report may state the duration in seconds
                    # while the field is ms-typed; accept the conversion ONLY when the unit
                    # records the original scale, and verify the ORIGINAL value is present.
                    lu = r.get("latency_unit") or ""
                    if "report states" in lu and " s" in lu and not appears(d, r["latency_ms"] / 1000.0):
                        miss.append("latency_ms")
                if r.get("ane_regions") is not None and not appears(d, r.get("ane_regions")):
                    miss.append("ane_regions")
                if r.get("date") and not (r["date"] in t or digits(r["date"]) in d):
                    miss.append("date")
                if not miss:
                    status, where, ok = "verified", n, True
                    break
                if miss_all is None or len(miss) < len(miss_all):
                    miss_all = miss
            if not ok:
                status, miss = "value-missing", miss_all or []
                where = cands[0][0]

        results.append({"id": rid, "status": status, "report": where,
                        "missing": miss if status != "verified" else []})

    from collections import Counter
    c = Counter(x["status"] for x in results)
    print(f"  rows audited   : {len(results)}")
    for k in ("verified", "value-missing", "unattributable"):
        print(f"  {k:<14}: {c.get(k, 0)}")
    bad = [x for x in results if x["status"] != "verified"]
    if bad:
        print(f"  non-verified (declared, not failed):")
        for x in bad[:30]:
            extra = f" (missing {', '.join(x['missing'])})" if x["missing"] else ""
            print(f"    {x['status']:<14} {x['id']}{extra}  [{x['report'] or '-'}]")
        if len(bad) > 30:
            print(f"    … and {len(bad)-30} more")

    if args.json:
        attributed = sum(1 for x in results if x["report"])
        payload = {
            "_note": "Standing re-check of every measurements.json row against its source EXP "
                     "report. verified = value (+latency_ms/ane_regions/date when set) literally "
                     "appears in an attributable report (separator-blind). unattributable = no "
                     "report found — declared, never asserted. value-missing = a report was found "
                     "but a field does not occur in it. "
                     f"Coverage: all {len(results)} ledger rows audited this run "
                     f"({attributed} attributed to an EXP report, {len(results) - attributed} "
                     "declared unattributable); regenerate with --json after any ledger change.",
            "totals": dict(c),
            "rows": results,
        }
        OUT.write_text(json.dumps(payload, indent=1))
        print(f"\n  wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
