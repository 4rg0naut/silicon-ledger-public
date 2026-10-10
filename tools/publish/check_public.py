#!/usr/bin/env python3
"""check_public.py — the gates for the PUBLIC mirror (staging tree).

Owner's framing (2026-10-10): the public repo is a *friendly distillation*, not a readable copy of
the corpus — its honesty layer (novelty statuses, receipts) stays, but its front door must be clean.
Two rules make that enforceable instead of aspirational:

  LINKS     every relative link in a published .md must resolve inside the published tree.
            Exempt: pinned third-party material under `results/**/raw/**` (those READMEs link into
            their own projects, not ours).
  NOVELTY   every row of the findings table in WHATSNEW.md must carry a status of NEW / EXT / KNOWN
            and an evidence link that resolves — so no headline ships without its novelty label.
            This is the anti-overclaim rule: claiming a known thing as new is the failure mode.

usage: python3 tools/publish/check_public.py [--staging PATH]     # default: ../silicon-ledger-public-staging
exit:  0 = clean, 1 = violations (publish must not proceed)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent          # silicon-ledger/
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
STATUS = re.compile(r"\b(NEW|EXT|KNOWN)\b")


def is_exempt(rel: str) -> bool:
    """Pinned third-party material: its links belong to other projects."""
    return "/raw/" in rel or rel.startswith("results/") and "/raw/" in rel


def check_links(stage: Path) -> list[str]:
    bad = []
    for p in sorted(stage.rglob("*.md")):
        rel = os.path.relpath(p, stage)
        if is_exempt(rel):
            continue
        text = p.read_text(errors="replace")
        for target in LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:", "#", "tel:", "?")):
                continue
            t = target.split("#")[0].split("?")[0]
            if not t:
                continue
            if t.startswith("/"):                      # root-relative: resolve from staging root
                resolved = stage / t.lstrip("/")
            else:
                resolved = (p.parent / t).resolve()
            if not Path(resolved).exists():
                bad.append(f"{rel}: dead link -> {target}")
    return bad


def check_novelty(stage: Path) -> list[str]:
    bad = []
    whatsnew = stage / "WHATSNEW.md"
    if not whatsnew.exists():
        return ["WHATSNEW.md missing from the public tree"]
    # findings rows look like: | 12 | **Finding** ... | **NEW** | [`file`](path) |
    for line in whatsnew.read_text(errors="replace").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or not cells[0].isdigit() or cells[0] == "#":
            continue
        num, _, status, evidence = cells[0], cells[1], cells[2], cells[-1]
        if not STATUS.search(status):
            bad.append(f"WHATSNEW row {num}: no NEW/EXT/KNOWN status (got {status!r})")
        links = LINK.findall(evidence)
        if not links:
            bad.append(f"WHATSNEW row {num}: no evidence link")
        for t in links:
            if t.startswith("http"):
                continue
            resolved = stage / t.lstrip("/") if t.startswith("/") else (whatsnew.parent / t)
            if not Path(resolved).exists():
                bad.append(f"WHATSNEW row {num}: evidence link does not resolve -> {t}")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--staging", default=str(ROOT.parent / "silicon-ledger-public-staging"))
    a = ap.parse_args()
    stage = Path(a.staging)
    if not stage.is_dir():
        print(f"no staging tree at {stage}")
        return 1
    links, novelty = check_links(stage), check_novelty(stage)
    for label, bad in (("LINKS", links), ("NOVELTY", novelty)):
        if bad:
            print(f"FAIL {label}: {len(bad)} violation(s)")
            for b in bad[:15]:
                print(f"  {b}")
            if len(bad) > 15:
                print(f"  … {len(bad) - 15} more")
        else:
            print(f"OK   {label}")
    return 1 if (links or novelty) else 0


if __name__ == "__main__":
    sys.exit(main())
