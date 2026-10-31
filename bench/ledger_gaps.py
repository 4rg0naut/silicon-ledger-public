#!/usr/bin/env python3
"""ledger_gaps.py — close ledger gaps only where a source states the fact literally; declare the rest.

For each row of results/measurements.json (after bench/normalize_enums.py --apply):
  * undated  -> `date` is set ONLY for rows of ours whose id appears verbatim in their attributed EXP
    README, and that README carries one literal `**Run:** YYYY-MM-DD` line; `date_source` records
    `results/<EXP>/README.md:<line>`. Third-party / vendor rows are never dated from our run date.
  * hardware_id unknown -> set to `m4-base` ONLY for rows of ours whose attributed README's Run line
    literally says `base M4`; `hardware_source` records the file:line. Otherwise stays `unknown`.
  * not verified by bench/audit_measurements.py -> `unverified_reason` states the audit status and
    the cause that can be derived from the data (never invented).
Nothing legacy is rewritten: the original `date` stays null, `hardware` stays as is; only new
fields (`date_source`, `hardware_source`, `unverified_reason`) are added, and `date` is filled only
where it was null. Dry-run unless --apply. Always rewrites docs/reshape/LEDGER-GAPS.md.

usage:
    python3 bench/audit_measurements.py --json
    python3 bench/ledger_gaps.py            # dry-run + report
    python3 bench/ledger_gaps.py --apply
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
REPORT = ROOT / "docs" / "reshape" / "LEDGER-GAPS.md"
RUN_RE = re.compile(r"\*\*Run:\*\*\s*(20\d\d-\d\d-\d\d)")


def readme_lines(rep):
    return (ROOT / "results" / rep / "README.md").read_text(errors="replace").splitlines()


def run_line(rep):
    for i, l in enumerate(readme_lines(rep), 1):
        m = RUN_RE.search(l)
        if m:
            return i, m.group(1), l
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    doc = json.loads(DATA.read_text())
    rows = doc["measurements"]
    aud = {r["id"]: r for r in json.loads(AUDIT.read_text())["rows"]}
    if any("hardware_id" not in r for r in rows):
        print("refusing: run bench/normalize_enums.py --apply first", file=sys.stderr)
        return 2

    dated, hwset, reasons = [], [], []
    undated_left, hw_left = [], []
    for r in rows:
        au = aud[r["id"]]
        rep = au["report"]
        rl = run_line(rep) if rep else None
        if not r.get("date"):
            ok = (rep and rl and r["provenance_class"] == "ours"
                  and any(r["id"] in l for l in readme_lines(rep)))
            if ok:
                dated.append((r, rl[1], f"results/{rep}/README.md:{rl[0]}"))
            else:
                undated_left.append(r)
        if r["hardware_id"] == "unknown":
            ok = rep and rl and r["provenance_class"] == "ours" and "base M4" in rl[2]
            if ok:
                hwset.append((r, f"results/{rep}/README.md:{rl[0]}"))
            else:
                hw_left.append(r)
        if au["status"] != "verified":
            miss = au["missing"]
            if au["status"] == "unattributable":
                why = ("no EXP README names this id or holds its value together with its model/metric; "
                       f"provenance_class={r['provenance_class']}")
                if r["provenance_class"] in ("vendor", "third-party", "external-paper"):
                    why += " (external number, labelled, not our measurement)"
            else:
                why = (f"value-missing in {rep}: {', '.join(miss) or 'a field'} does not literally appear "
                       f"in the report; provenance_class={r['provenance_class']}")
            reasons.append((r, why))

    dated_ids = {r["id"] for r, _, _ in dated}
    hw_ids = {r["id"] for r, _ in hwset}
    print(f"dateable now: {len(dated)}  | still undated: {len(undated_left)}")
    print(f"hardware set now: {len(hwset)}  | hardware unknown left: {len(hw_left)}")
    print(f"unverified reasons: {len(reasons)}")

    if a.apply:
        by = {r["id"]: r for r in rows}
        for r, d, src in dated:
            by[r["id"]]["date"] = d
            by[r["id"]]["date_source"] = src
        for r, src in hwset:
            by[r["id"]]["hardware_id"] = "m4-base"
            by[r["id"]]["hardware_source"] = src
        for r, why in reasons:
            by[r["id"]]["unverified_reason"] = why
        hist = doc.setdefault("_merge_history", [])
        if not any(h.get("tool") == "bench/ledger_gaps.py" for h in hist):
            hist.append({"tool": "bench/ledger_gaps.py", "date_backfilled": len(dated),
                         "hardware_id_from_source": len(hwset), "unverified_reason": len(reasons), "at": None})
        DATA.write_text(json.dumps(doc, indent=1))
        print("applied")

    L = ["# Ledger gaps — what is declared, and why", "",
         "Generated by `bench/ledger_gaps.py` from `results/measurements.json` and `results/audit_measurements.json`. "
         "Rebuild, never patch. Nothing was guessed: a fact is filled only where a source states it literally, "
         "and its location is stored in the row (`date_source`, `hardware_source`).", ""]
    L += ["## Undated rows", "",
          f"- backfilled from a literal `**Run:**` line (rows of ours whose id appears in that README): **{len(dated)}**"]
    for r, d, src in dated:
        L.append(f"  - `{r['id']}` -> {d} (`{src}`)")
    L += [f"- still undated, declared: **{len(undated_left)}**", "",
          "| provenance_class | rows | reason |", "|---|---|---|"]
    c = Counter(r["provenance_class"] for r in undated_left)
    why = {"third-party": "published or reproduced reference number: the README's Run date is when WE ran it, not the number's date",
           "vendor": "vendor claim: no measurement date exists in this repo",
           "ours": "row of ours without an id-literal README line carrying a date",
           "external-paper": "paper number", "mixed": "mixed row", "ours-bench": "bench report row", "unknown": "unclassified"}
    for k, v in c.most_common():
        L.append(f"| {k} | {v} | {why.get(k, '')} |")
    L += ["", "Undated ids (declared, none silently dated):", ""]
    L.append(", ".join(f"`{r['id']}`" for r in undated_left))
    L += ["", "## Rows without hardware", "",
          f"- `hardware_id` set to `m4-base` from a literal `base M4` Run line (rows of ours): **{len(hwset)}**",
          f"- stay `unknown` (no source states the machine): **{len(hw_left)}**", "",
          "| provenance_class | rows |", "|---|---|"]
    for k, v in Counter(r["provenance_class"] for r in hw_left).most_common():
        L.append(f"| {k} | {v} |")
    L += ["", "By attributed report:", "", "| report | rows |", "|---|---|"]
    for k, v in Counter(str(aud[r["id"]]["report"]) for r in hw_left).most_common():
        L.append(f"| {k} | {v} |")
    L += ["", "## Non-verified rows (21 value-missing + 34 unattributable at baseline)", "",
          f"{len(reasons)} rows carry `unverified_reason`. None was dropped or promoted.", "",
          "| audit status | rows |", "|---|---|"]
    for k, v in Counter(aud[r["id"]]["status"] for r, _ in reasons).most_common():
        L.append(f"| {k} | {v} |")
    L += ["", "| row | status | reason |", "|---|---|---|"]
    for r, w in reasons:
        L.append(f"| `{r['id']}` | {aud[r['id']]['status']} | {w} |")
    L += ["", "## In-flight and structural exceptions", "",
          "- `results/EXP-038-nax-quiet-retake/` has no README by design: its certified-quiet window is still running "
          "(see `STATE.md`); the audit and the ledger carry no EXP-038 numbers. It is an in-flight exception, not a gap.",
          "- Duplicate EXP-023 ids (`EXP-023-small-llm-ane-pilot`, `EXP-023-m5max-energy`) and the unclaimed EXP-030 "
          "are documented in `results/README.md` (EXP namespace reconciliation); an append-only note was added there.", ""]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(L) + "\n")
    print(f"wrote {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
