#!/usr/bin/env python3
"""Extract and validate the knowledge base's machine layer.

Every document in knowledge/ane/ carries two layers in one file: prose for humans, and a
fenced ```jsonl block of atomic claims for machines. This tool pulls those blocks out
mechanically and checks them. No model is involved and none should ever be -- this is the
part of the pipeline that must be boring and reproducible.

    python tools/kb_records.py extract     write records/ from the markdown
    python tools/kb_records.py validate    check schema and hygiene, print a report
    python tools/kb_records.py             both

Exit code is non-zero when a hard check fails, so it can gate a commit.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT
RECORDS = KB / "records"

KINDS = {"fact", "definition", "procedure", "gotcha", "measurement", "open-question"}
CONFIDENCE = {"measured", "documented", "inferred", "claimed"}
SOURCE_TYPES = {"primary", "secondary", "our-own"}
SPLITS = {"train", "holdout"}

REQUIRED = ["id", "claim", "kind", "confidence", "source", "source_type",
            "retrieved", "topic", "entities", "split"]

BLOCK = re.compile(r"```jsonl\n(.*?)```", re.S)

# A claim should be ONE self-contained sentence. These are heuristics for flagging
# likely compounds, not hard errors -- some claims legitimately contain a semicolon.
SENTENCE_ENDS = re.compile(r"[.!?]\s+[A-Z]")
CONJUNCT = re.compile(r";\s*(and|but|while|whereas)\b", re.I)


# Files that are ABOUT the knowledge base rather than part of it. They carry no records
# and must not be reported as if they were missing them.
NON_CONTENT = {"README.md", "00-DESIGN.md", "SOURCES.md"}


def docs() -> list[Path]:
    return sorted(p for p in KB.glob("*.md") if p.name not in NON_CONTENT)


def load() -> tuple[list[dict], list[str]]:
    recs, problems = [], []
    for p in docs():
        text = p.read_text(encoding="utf-8")
        blocks = BLOCK.findall(text)
        if not blocks:
            problems.append(f"{p.name}: no ```jsonl block")
            continue
        for b in blocks:
            for i, line in enumerate(b.strip().splitlines(), 1):
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError as e:
                    problems.append(f"{p.name} line {i}: JSON error: {e}")
                    continue
                r["_file"] = p.name
                # Documented defaults: `split` defaults to "train" (see 00-DESIGN.md). Applying
                # the default here rather than failing keeps the validator honest -- a missing
                # field with a defined default is not a defect, and treating it as one trains
                # people to ignore the report.
                r.setdefault("split", "train")
                recs.append(r)
    return recs, problems


def validate(recs: list[dict]) -> tuple[list[str], list[str], list[str]]:
    hard: list[str] = []    # must fix
    soft: list[str] = []    # worth a look
    stats: list[str] = []

    ids = [r.get("id", "?") for r in recs]
    dupes = [i for i, c in Counter(ids).items() if c > 1]
    if dupes:
        hard.append(f"duplicate ids: {dupes[:10]}")

    for r in recs:
        rid = r.get("id", f"<{r['_file']} line?>")
        for f in REQUIRED:
            if f not in r or r[f] in ("", None, []):
                hard.append(f"{rid}: missing/empty '{f}'")
        if r.get("kind") and r["kind"] not in KINDS:
            hard.append(f"{rid}: bad kind '{r['kind']}'")
        if r.get("confidence") and r["confidence"] not in CONFIDENCE:
            hard.append(f"{rid}: bad confidence '{r['confidence']}'")
        if r.get("source_type") and r["source_type"] not in SOURCE_TYPES:
            hard.append(f"{rid}: bad source_type '{r['source_type']}'")
        if r.get("split") and r["split"] not in SPLITS:
            hard.append(f"{rid}: bad split '{r['split']}'")
        if not isinstance(r.get("topic"), list):
            hard.append(f"{rid}: topic must be a list")
        if not isinstance(r.get("entities"), list):
            hard.append(f"{rid}: entities must be a list")

        claim = r.get("claim", "")
        if claim and len(claim) < 25:
            soft.append(f"{rid}: claim looks too short to be self-contained")
        if claim and SENTENCE_ENDS.search(claim):
            soft.append(f"{rid}: claim may hold more than one sentence")
        if CONJUNCT.search(claim):
            soft.append(f"{rid}: claim may be compound")
        # Deliberately NOT checked: "does the claim start with a capital letter". It was
        # tried, and rejected ~50 good claims while finding nothing -- project names are
        # lowercase ("ane-probe builds ...") and Objective-C selectors start with + or -
        # ("+inMemoryModelWithDescriptor: is ..."). A check that only cries wolf is worse
        # than no check, because it trains you to ignore the report.
        # `measured` needs evidence; that is the whole point of the label
        if r.get("confidence") == "measured" and not r.get("evidence"):
            soft.append(f"{rid}: confidence=measured but no evidence field")

    n = len(recs) or 1
    stats.append(f"records: {len(recs)}")
    stats.append(f"by confidence: {dict(Counter(r.get('confidence','?') for r in recs))}")
    stats.append(f"by kind:       {dict(Counter(r.get('kind','?') for r in recs))}")
    stats.append(f"by source_type:{dict(Counter(r.get('source_type','?') for r in recs))}")
    stats.append(f"split: {dict(Counter(r.get('split','train') for r in recs))}  "
                 f"(holdout {Counter(r.get('split','train') for r in recs).get('holdout',0)}/{len(recs)}"
                 f" = {100*Counter(r.get('split','train') for r in recs).get('holdout',0)/n:.1f}%)")
    stats.append(f"contested: {sum(1 for r in recs if r.get('contested'))}")
    sources = {r.get("source") for r in recs if r.get("source")}
    stats.append(f"distinct sources: {len(sources)}")
    return hard, soft, stats


def main() -> int:
    recs, parse_problems = load()
    hard, soft, stats = validate(recs)

    print("=== summary ===")
    for s in stats:
        print(f"  {s}")

    if parse_problems:
        print(f"\n=== parse problems ({len(parse_problems)}) ===")
        for p in parse_problems[:20]:
            print(f"  {p}")

    if soft:
        print(f"\n=== worth a look ({len(soft)}) ===")
        for s in soft[:40]:
            print(f"  {s}")
        if len(soft) > 40:
            print(f"  ... and {len(soft)-40} more")

    if hard:
        print(f"\n=== MUST FIX ({len(hard)}) ===")
        for h in hard[:40]:
            print(f"  {h}")
    else:
        print("\n  no hard failures")

    if "extract" in sys.argv or len(sys.argv) == 1:
        RECORDS.mkdir(exist_ok=True)
        for p in docs():
            out = RECORDS / (p.stem + ".jsonl")
            blocks = BLOCK.findall(p.read_text(encoding="utf-8"))
            lines = []
            for b in blocks:
                for line in b.strip().splitlines():
                    line = line.strip()
                    if line and not line.startswith("//"):
                        try:
                            json.loads(line); lines.append(line)
                        except json.JSONDecodeError:
                            pass
            if lines:
                out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        merged = RECORDS / "all.jsonl"
        merged.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
        print(f"\n  wrote {len(recs)} records to {RECORDS}/")

    return 1 if (hard or parse_problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())