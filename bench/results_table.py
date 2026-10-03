#!/usr/bin/env python3
"""Generate comparison tables from a measurement schema, so no number is hand-maintained.

Why this exists: the EXP-* reports were written one at a time, and their tables drifted. Audited
2026-09-22, the same column held latencies measured per-decision, per-embedding, per-pair and
per-option-pass; 6 of 18 reports named no benchmark; none stated the split; 6 named no hardware;
and our JevBench rows are public-only (231 of 534) while the leaderboard is the full set. None of
that is visible in a hand-written table.

The schema forces every one of those to be explicit, and `--compare` refuses to rank rows that are
not actually comparable.

usage:
    python bench/results_table.py                 # all rows, grouped by comparability class
    python bench/results_table.py --compare NAME  # only rows comparable to a named row
    python bench/results_table.py --gaps          # what is missing, per class
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "results" / "measurements.json"

# ---------------------------------------------------------------- schema
# Every field that a table could hide, made mandatory. `null` is allowed but is PRINTED as "—" and
# counted as a gap, so an unknown is never silently rendered as if it were measured.
FIELDS = (
    "id", "model", "checkpoint", "params_m",
    "runtime", "placement", "dtype", "seq_len", "ane_regions",
    "benchmark", "split", "scope", "tiers",
    "metric", "value", "unit",
    "latency_ms", "latency_unit", "hardware", "load_factor",
    "energy_mw", "energy_rail", "energy_baseline",
    "provenance", "date", "command", "protocol", "unit_kind",
)

# Rows are comparable only when all of these agree. Anything else is context, not a ranking.
COMPARE_KEYS = ("benchmark", "split", "scope", "tiers", "metric", "unit", "latency_unit")

# Two levels of completeness. FLOOR is the minimum every row in the ledger meets
# (enforced at merge time by verify_extraction, and by the builder for new rows):
# below it, a row is unusable. BUILDER_FLOOR is what the builder additionally
# enforces on NEW rows (model + benchmark). 422 legacy extracted rows predate it
# and lack model/benchmark — reported as curation debt, not as an error. The
# rest of FIELDS is context a table could hide (protocol, load_factor, energy
# rails, ...); lacking it is incomplete, not wrong.
FLOOR = ("id", "metric", "value", "unit", "provenance")
BUILDER_FLOOR = FLOOR + ("model", "benchmark")


def load() -> list[dict]:
    return json.loads(DATA.read_text())["measurements"]


def cell(v) -> str:
    if v is None or v == "":
        return "—"
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def gaps(rows: list[dict]) -> dict:
    """Which mandatory fields are unset, per row — the honest completeness measure."""
    out = {}
    for r in rows:
        missing = [f for f in FIELDS if r.get(f) in (None, "")]
        if missing:
            out[r["id"]] = missing
    return out


def comparable_to(rows: list[dict], name: str) -> list[dict]:
    """Rows sharing the reference row's comparability class.

    Uses the SAME normalisation as --summary (keys_for: case/whitespace/punctuation
    folded, scope canonicalised, latency_unit metric-dependent), so a formatting
    variant groups here exactly as it groups in the summary. Deliberately STRICTER
    than --summary's wildcard: an unstated (null) key is NOT treated as "matches
    anything" here — --summary flags that as "grouping uncertain", and a
    side-by-side comparison should not rest on an unflagged assumption.
    """
    ref = next((r for r in rows if r["id"] == name), None)
    if ref is None:
        raise SystemExit(f"no row named {name!r}")
    ref_key = keys_for(ref)
    return [r for r in rows if keys_for(r) == ref_key]


def table(rows: list[dict], cols: tuple[str, ...]) -> str:
    head = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    body = ["| " + " | ".join(cell(r.get(c)) for c in cols) + " |" for r in rows]
    return "\n".join([head, sep, *body])


def norm_key(v):
    """Canonicalise a comparability key so formatting variants group together.

    Observed in practice: the same metric arrived as "chance-corrected 0-100" and
    "chance-corrected, 0-100" from two different extractors, which split one comparison into two
    groups. Normalising case, whitespace and list punctuation fixes that.

    Deliberately conservative — it must NOT merge genuinely different units. "per decision (all
    options in one pass)" and "per decision (N option passes)" stay distinct, because that
    difference is the whole point of the field.
    """
    if v is None:
        return None
    s = " ".join(str(v).lower().split())
    return s.replace(",", " ").replace(";", " ").replace("  ", " ").strip()


def norm_scope(v):
    """`231 of 534 items` and `231 of 534` are the same scope written two ways."""
    if v is None:
        return None
    s = norm_key(v)
    return re.sub(r"\s*(items?|rows?|samples?)$", "", s).strip()


LATENCY_METRICS = ("latency", "p50", "p95", "ms", "load")


def keys_for(r: dict) -> tuple:
    """The comparability key, which is METRIC-DEPENDENT.

    `latency_unit` decides whether two *latency* numbers mean the same thing — Von's N option
    passes is genuinely not Laya's single pass. But it says nothing about an *accuracy* metric, and
    including it there split an Intelligence comparison in two for no reason. So it is part of the
    key only when the metric is a latency.
    """
    metric = (r.get("metric") or "").lower()
    ks = [k for k in COMPARE_KEYS
          if k != "latency_unit" or any(w in metric for w in LATENCY_METRICS)]
    return tuple(norm_scope(r.get(k)) if k == "scope" else norm_key(r.get(k)) for k in ks)


def class_of(r: dict) -> tuple:
    return keys_for(r)


# Only fields whose ABSENCE is a formatting gap may be wildcarded. `tiers` is deliberately NOT
# here: a 3-tier Intelligence and a 4-tier Intelligence are different quantities, so merging them
# would put JevBench's published 45.8 beside our 41.5 as if they were the same measurement. Same
# for `metric`, `unit` and `latency_unit` — those define the number, they do not decorate it.
# A tuple (not a set): iteration order feeds the "grouping uncertain" line in --summary,
# and a frozenset's order is hash-randomised per process, which made the generated file churn.
WILDCARDABLE = ("split", "scope")


def group_rows(rows: list[dict]) -> dict[tuple, list[dict]]:
    """Group by comparability key, treating `None` as a WILDCARD.

    `None` means "the report did not state it" — it does not mean "it differs". Treating it as a
    distinguishing value shattered one JevBench comparison into five groups over a comma and an
    omitted `tiers`. But a wildcard is an assumption, so `--summary` marks any group whose rows
    disagree on a key it wildcarded. The reader is told the grouping is uncertain rather than
    being handed a clean table that quietly rests on a guess.
    """
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        # wildcard: a row missing a key joins the first group whose present keys all match
        placed = False
        for key, members in groups.items():
            ok = True
            for k, kv in zip([k for k in COMPARE_KEYS
                              if k != "latency_unit" or any(
                                  w in (r.get("metric") or "").lower() for w in LATENCY_METRICS)], key):
                rv = norm_scope(r.get(k)) if k == "scope" else norm_key(r.get(k))
                if kv is not None and rv is not None and kv != rv:
                    ok = False
                    break
                if kv is not None and rv is None:
                    if k in WILDCARDABLE:
                        continue      # formatting gap — allowed, flagged below
                    ok = False        # definitional gap — must NOT be merged
                    break
            if ok:
                members.append(r)
                placed = True
                break
        if not placed:
            groups[class_of(r)] = [r]
    return groups


def summary(rows: list[dict]) -> str:
    """Group by comparability class; emit only classes holding a real comparison (>=2 rows).

    A class of one is not a comparison — it is a lone number, and showing it beside others is how
    the old tables implied comparability that did not exist.
    """
    groups = group_rows(rows)
    comparable = {k: v for k, v in groups.items() if len(v) >= 2}
    lone = len(rows) - sum(len(v) for v in comparable.values())

    out = ["# Every measurement, grouped by what is actually comparable", "",
           f"Generated by `bench/results_table.py --summary` from `results/measurements.json` "
           f"({len(rows)} records). **Do not hand-edit** — regenerate instead.", "",
           f"Rows are grouped only when `{' + '.join(COMPARE_KEYS)}` all agree. "
           f"**{sum(len(v) for v in comparable.values())} records form {len(comparable)} real "
           f"comparisons; {lone} are lone measurements** shown nowhere below, because a single "
           f"number beside others is how a false comparison starts.", ""]
    for key, rs in sorted(comparable.items(), key=lambda kv: -len(kv[1])):
        # group on the normalised key, DISPLAY the original casing from a representative row
        rep = rs[0]
        # the key is variable-length (metric-dependent); display from a representative row
        bench, split, scope = rep.get("benchmark"), rep.get("split"), rep.get("scope")
        tiers, metric, unit = rep.get("tiers"), rep.get("metric"), rep.get("unit")
        lu = rep.get("latency_unit")
        out.append(f"## {rep.get('benchmark') or 'benchmark unstated'} — "
                   f"{rep.get('metric')} ({rep.get('unit')})")
        out.append("")
        unstated = [c for c in WILDCARDABLE
                    if any(norm_key(r.get(c)) is None for r in rs)
                    and any(norm_key(r.get(c)) is not None for r in rs)]
        flag = (f"  ⚠ **grouping uncertain** — some rows leave "
                f"{', '.join('`'+u+'`' for u in unstated)} unstated; they are grouped here "
                f"because unstated is not the same as different.") if unstated else ""
        lat_bit = f" · latency: {lu}" if any(
            w in (metric or "").lower() for w in LATENCY_METRICS) else ""
        out.append(f"*split: {split or 'unstated'} · scope: {scope or 'unstated'} · "
                   f"tiers: {tiers or 'n/a'}{lat_bit}*{flag}")
        out.append("")
        out.append(table(rs, ("model", "placement", "dtype", "seq_len", "value",
                              "latency_ms", "hardware", "provenance", "id")))
        out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare", default=None)
    ap.add_argument("--gaps", action="store_true")
    ap.add_argument("--summary", action="store_true",
                    help="write results/SUMMARY.md, grouped by comparability class")
    args = ap.parse_args()

    if args.summary:
        rows = load()
        out = summary(rows)
        (ROOT / "results" / "SUMMARY.md").write_text(out)
        n = out.count("\n## ")
        print(f"  wrote results/SUMMARY.md  ({n} comparison groups, {len(rows)} records scanned)")
        return 0

    rows = load()
    print(f"  {len(rows)} measurement records\n")

    if args.gaps:
        g = gaps(rows)
        floor_bad = {rid: [f for f in missing if f in FLOOR]
                     for rid, missing in g.items() if any(f in FLOOR for f in missing)}
        legacy = [rid for rid, missing in g.items()
                  if not any(f in FLOOR for f in missing)
                  and any(f in BUILDER_FLOOR for f in missing)]
        print("  GAPS (schema fields left unset; null = NOT MEASURED):")
        if not g:
            print("    none")
        for rid, missing in g.items():
            print(f"    {rid:<28} {', '.join(missing)}")
        print(f"\n  below universal floor       : {len(floor_bad)}/{len(rows)} records"
              + (f"  ->  {', '.join(sorted(floor_bad))}" if floor_bad else "  (none)"))
        print(f"  below builder floor (legacy): {len(legacy)}/{len(rows)} records "
              f"(model/benchmark unset; curation debt, not error)")
        print(f"  incomplete incl. context    : {len(g)}/{len(rows)} records "
              f"(protocol / load_factor / energy rails usually unset by design)")
        return 0

    if args.compare:
        rows = comparable_to(rows, args.compare)
        print(f"  comparable to {args.compare!r}: {len(rows)} rows "
              f"(same normalised comparability class as --summary)\n")

    print(table(rows, ("id", "model", "runtime", "placement", "dtype", "seq_len",
                       "metric", "value", "latency_ms", "latency_unit", "hardware",
                       "provenance")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
