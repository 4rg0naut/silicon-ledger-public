#!/usr/bin/env python3
"""normalize_enums.py — add canonical hardware_id / provenance_class / project to every ledger row.

Append-only: the legacy `hardware` and `provenance` strings are never modified. New fields are added
at the end of each row; a `_merge_history` entry records the change. Unmappable values are reported and
mapped to `unknown` / `unattributed`, never guessed. Dry-run unless --apply.

`project` needs the attributed report of each row: run `python3 bench/audit_measurements.py --json`
first (this script refuses to run if the audit file does not cover every row id).

usage:
    python3 bench/normalize_enums.py            # dry-run: print the mapping and unmappable values
    python3 bench/normalize_enums.py --apply    # write the three fields + _merge_history entry
Note: `bench/build_measurements.py --force` rebuilds rows from its fixed KEYS and would drop these
fields; use it only with --apply-new (default is non-destructive).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "results" / "measurements.json"
AUDIT = ROOT / "results" / "audit_measurements.json"
ENUMS = ROOT / "schemas" / "enums"
NEW_FIELDS = ("hardware_id", "provenance_class", "project")


def load_enums():
    hw = json.loads((ENUMS / "hardware.json").read_text())
    pv = json.loads((ENUMS / "provenance.json").read_text())
    pj = json.loads((ENUMS / "project.json").read_text())
    return hw, pv, pj


def hardware_id(row, hw):
    s = row.get("hardware")
    if not s:
        return "unknown", "no hardware string"
    if s in hw["aliases"]:
        return hw["aliases"][s], None
    return "unknown", f"unmapped hardware string {s!r}"


def provenance_class(row, pv):
    s = row.get("provenance") or ""
    for rule in pv["rules"]:
        if rule["match"] == "prefix" and s.startswith(rule["text"]):
            return rule["class"], None
        if rule["match"] == "contains" and rule["text"] in s:
            return rule["class"], None
    return "unknown", f"unmapped provenance string {s!r}"


def exp_dirs():
    return sorted(p.name for p in (ROOT / "results").glob("EXP-*") if p.is_dir())


def project_of(row, report, pj, dirs):
    ports = set(pj["exp_dirs"]["ports"])
    d = report
    how = "audit report"
    if not d:
        cmd = str(row.get("command") or "")
        hit = [x for x in dirs if x in cmd]
        if not hit:
            nums = set(re.findall(r"EXP-(\d{3})", cmd))
            hit = [x for n in nums for x in dirs if x.startswith(f"EXP-{n}-")]
            hit = hit if len({h[:7] for h in hit}) == len(hit) else []
        if len(hit) == 1:
            d, how = hit[0], "command"
    if not d:
        m = re.match(r"exp(\d{3})-", row.get("id") or "")
        if m:
            hit = [x for x in dirs if x.startswith(f"EXP-{m.group(1)}-")]
            if len(hit) == 1:
                d, how = hit[0], "id prefix"
    if not d:
        return "unattributed", "no report, command or id names an experiment"
    if d not in dirs:
        return "unattributed", f"{d} is not a results/ directory"
    return ("ports" if d in ports else "hw-lanes"), f"{how}: {d}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    hw, pv, pj = load_enums()
    doc = json.loads(DATA.read_text())
    rows = doc["measurements"]
    if not AUDIT.exists():
        print("refusing: run bench/audit_measurements.py --json first", file=sys.stderr)
        return 2
    aud = {r["id"]: r.get("report") for r in json.loads(AUDIT.read_text())["rows"]}
    missing = [r["id"] for r in rows if r["id"] not in aud]
    if missing:
        print(f"refusing: audit file lacks {len(missing)} row ids (re-run audit --json): {missing[:3]}", file=sys.stderr)
        return 2
    dirs = exp_dirs()

    out = []
    unm = Counter()
    for r in rows:
        h, hn = hardware_id(r, hw)
        p, pn = provenance_class(r, pv)
        j, jn = project_of(r, aud[r["id"]], pj, dirs)
        if hn and "unmapped" in hn:
            unm[hn] += 1
        if pn:
            unm[pn] += 1
        out.append((r, h, p, j))

    ch, cp, cj = (Counter(x[i] for x in out) for i in (1, 2, 3))
    print(f"rows: {len(rows)}")
    print("hardware_id     :", dict(ch))
    print("provenance_class:", dict(cp))
    print("project         :", dict(cj))
    print(f"distinct legacy hardware strings: {len({r.get('hardware') for r in rows})} -> "
          f"{len(ch)} hardware_id values")
    if unm:
        print("UNMAPPED:")
        for k, v in unm.items():
            print(f"  {v} x {k}")

    already = [r for r in rows if all(f in r for f in NEW_FIELDS)]
    if not a.apply:
        print(f"dry-run: {len(already)} rows already carry the fields; nothing written (use --apply)")
        return 0

    orig = {r["id"]: (r.get("hardware"), r.get("provenance")) for r in rows}
    changed = 0
    for r, h, p, j in out:
        for f, v in zip(NEW_FIELDS, (h, p, j)):
            if r.get(f) != v:
                r[f] = v
                changed += 1
    assert all(orig[r["id"]] == (r.get("hardware"), r.get("provenance")) for r in rows), "legacy field changed"
    hist = doc.setdefault("_merge_history", [])
    if changed and not any(h.get("tool") == "bench/normalize_enums.py" for h in hist):
        hist.append({"tool": "bench/normalize_enums.py", "added_fields": list(NEW_FIELDS),
                     "rows": len(rows), "legacy_fields_untouched": ["hardware", "provenance"], "at": None})
    DATA.write_text(json.dumps(doc, indent=1))
    print(f"applied: {changed} field values set across {len(rows)} rows; legacy hardware/provenance unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
