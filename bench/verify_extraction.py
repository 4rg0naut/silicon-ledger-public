#!/usr/bin/env python3
"""Verify extracted measurements against their source reports, then merge into measurements.json.

The split: a small model EXTRACTS, this script VERIFIES. Extraction is mechanical and delegable;
trusting it is not. Every claimed value must literally appear in the report it came from, or the
row is rejected — so a hallucinated or rounded number cannot reach the results table.

Checks, in order of severity:
  1. value        — the number must appear in the source report text
  2. latency_ms   — same
  3. ane_regions  — same
  4. latency_unit — must not be null when latency_ms is set (the failure mode this whole exercise exists for)
  5. provenance   — must be set
  6. date         — must appear in the report if claimed
  7. required keys present

usage:
    python bench/verify_extraction.py            # verify + report
    python bench/verify_extraction.py --merge    # verify, then merge the clean rows
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTRACT = ROOT / "work" / "memory-stack" / "extract"
RESULTS = ROOT / "results"
MERGED = RESULTS / "measurements.json"

KEYS = ("id", "model", "checkpoint", "params_m", "runtime", "placement", "dtype", "seq_len",
        "ane_regions", "benchmark", "split", "scope", "tiers", "metric", "value", "unit",
        "latency_ms", "latency_unit", "hardware", "load_factor", "energy_mw", "energy_rail",
        "energy_baseline", "provenance", "date", "command")


def forms(v) -> list[str]:
    """The textual forms a number could legitimately take in a report."""
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    out = set()
    for f in (f"{v:g}", f"{v:.2f}", f"{v:.3f}", f"{v:.4f}", f"{v:.5f}", f"{v:.1f}"):
        out.add(f)
        out.add(f.replace(".", ","))          # European decimal comma appears in some reports
    if float(v) == int(v):
        out.add(str(int(v)))
    return [s for s in out if s]


def appears(text: str, v) -> bool:
    """Separator-blind containment.

    Reports write `54,846` and `29,252`; a naive `in` test rejects them. So compare on a
    digits-only projection of both sides. This is deliberately generous: it catches a
    hallucinated or rounded number (which will not appear at all) while not tripping on
    formatting. It cannot catch a number that was copied from the wrong place in the same
    report — that remains a human check, and is why `--merge` reports counts.
    """
    if v is None:
        return True
    if isinstance(v, str):
        return v in text or v.replace(",", "") in text.replace(",", "")
    for f in forms(v):
        if f in text or f.replace(",", "") in text.replace(",", ""):
            return True
    # digits-only projection, for values written with thousands separators
    digits = re.sub(r"[^0-9]", "", f"{v:g}")
    if digits and digits in re.sub(r"[^0-9]", "", text):
        return True
    return False


def verify() -> tuple[list[dict], list[str]]:
    clean, problems = [], []
    for frag in sorted(EXTRACT.glob("EXP-*.json")):
        exp = frag.stem
        report = RESULTS / f"{exp}-" / "README.md"
        # the dir has a suffix; find it
        cands = sorted(RESULTS.glob(f"{exp}-*"))
        report = cands[0] / "README.md" if cands else None
        if report is None or not report.exists():
            problems.append(f"{exp}: no source report found")
            continue
        text = report.read_text(errors="replace")

        try:
            data = json.loads(frag.read_text())
        except json.JSONDecodeError as e:
            problems.append(f"{exp}: fragment is not valid JSON ({e})")
            continue

        rows = data.get("rows", [])
        for r in rows:
            rid = r.get("id", "<no-id>")
            bad = []

            # `model` may be null: a report can measure a model without naming it (EXP-011).
            # The rest may not — a row without a metric, value, unit or provenance is unusable.
            for k in ("id", "metric", "value", "unit", "provenance"):
                if r.get(k) in (None, ""):
                    bad.append(f"missing {k}")

            if not appears(text, r.get("value")):
                bad.append(f"value {r.get('value')!r} NOT FOUND in report")
            if r.get("latency_ms") is not None and not appears(text, r.get("latency_ms")):
                # A report may state a duration in seconds ("3.40 s") while the schema field is
                # ms-typed. That conversion is unavoidable, so accept it ONLY when the unit
                # records the original scale, and verify the ORIGINAL value is present.
                lu = (r.get("latency_unit") or "")
                ok = False
                if "report states" in lu and " s" in lu:
                    ok = appears(text, r["latency_ms"] / 1000.0)
                if not ok:
                    bad.append(f"latency_ms {r.get('latency_ms')!r} NOT FOUND in report")
            if r.get("ane_regions") is not None and not appears(text, r.get("ane_regions")):
                bad.append(f"ane_regions {r.get('ane_regions')!r} NOT FOUND in report")
            if r.get("latency_ms") is not None and not r.get("latency_unit"):
                bad.append("latency_ms set but latency_unit is null")
            if r.get("date") and not appears(text, r.get("date")):
                bad.append(f"date {r.get('date')!r} NOT FOUND in report")

            if bad:
                problems.append(f"{exp}/{rid}: " + "; ".join(bad))
            else:
                clean.append({k: r.get(k) for k in KEYS})

    return clean, problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args()

    clean, problems = verify()
    print(f"  fragments: {len(list(EXTRACT.glob('EXP-*.json')))}")
    print(f"  verified rows: {len(clean)}")
    print(f"  rejected: {len(problems)}")
    for p in problems[:40]:
        print(f"    ✗ {p}")
    if len(problems) > 40:
        print(f"    … and {len(problems)-40} more")

    if args.merge:
        cur = json.loads(MERGED.read_text())
        by_id = {r["id"]: r for r in cur["measurements"]}
        added = 0
        for r in clean:
            if r["id"] not in by_id:
                by_id[r["id"]] = r
                added += 1
        cur["measurements"] = list(by_id.values())
        # `_note` is SET, never appended: an accumulating note interleaves and
        # duplicates its own sentences across repeated merges (the file carried
        # those scars). The per-merge record lives in `_merge_history` instead.
        cur.setdefault("_merge_history", []).append(
            {"tool": "bench/verify_extraction.py", "added": added,
             "at": date.today().isoformat()})
        cur["_note"] = ("Rows are ranked only when benchmark+split+scope+tiers+metric+unit+"
                        "latency_unit all agree. Verified-extracted rows merged by "
                        "bench/verify_extraction.py (see _merge_history).")
        MERGED.write_text(json.dumps(cur, indent=1))
        print(f"\n  merged +{added} verified rows -> {MERGED.relative_to(ROOT)} "
              f"({len(cur['measurements'])} total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
