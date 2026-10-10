#!/usr/bin/env python3
"""rewrite_links.py — publication-aware link rewriting (runs on the STAGING tree only).

The private originals are untouched: evidence paths in records must keep pointing at the real files.
This pass fixes the *published copy* so a reader never hits a link into a tree that was never
published.

Rules (markdown links only — prose mentions are left alone and covered by PUBLISH-POLICY.md):

  target resolves inside the staging tree            -> keep (nothing to do)
  target is a private-only tree (repos/ models/ .omp/ data/ work/ bench-inbox/ exp022-raw/)
      -> known upstream (repos/coreai-model-zoo -> github.com/john-rocky/coreai-model-zoo)
         else unlink: keep the link text, append " *(not published)*"
  target under an experiment's harness/ or a non-published raw/ file
      -> point at that experiment's README (root-relative) and append " *(source private)*"

usage: python3 tools/publish/rewrite_links.py [--staging PATH]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LINK = re.compile(r"(\[[^\]]*\]\()([^)\s]+)(\))")
PRIVATE_TREES = ("repos/", "models/", ".omp/", "data/", "work/", "bench-inbox/", "exp022-raw/")
UPSTREAM = {"repos/coreai-model-zoo/": "https://github.com/john-rocky/coreai-model-zoo/blob/main/",
            "repos/coreai-models/": "https://github.com/apple/coreai-models/blob/main/"}
PUBLISHED_EXT = {".md", ".json", ".txt", ".sh"}


def experiment_of(rel: str) -> str | None:
    m = re.match(r"(results/EXP-[^/]+)/", rel)
    return m.group(1) if m else None


def rewrite(stage: Path) -> int:
    changed = 0
    for p in sorted(stage.rglob("*.md")):
        rel = os.path.relpath(p, stage)
        if "/raw/" in rel:                      # pinned third-party material: not ours to edit
            continue
        text = orig = p.read_text(errors="replace")

        def repl(m: re.Match) -> str:
            pre, target, post = m.groups()
            if target.startswith(("http://", "https://", "mailto:", "#", "tel:")):
                return m.group(0)
            t = target.split("#")[0].split("?")[0]
            if not t:
                return m.group(0)
            resolved = stage / t.lstrip("/") if t.startswith("/") else (p.parent / t).resolve()
            if Path(resolved).exists():
                return m.group(0)                                   # published: leave it
            # 1) private tree -> upstream URL if we know one, else unlink
            for tree in PRIVATE_TREES:
                if t.startswith(tree) or f"/{tree}" in t:
                    for pre_u, url in UPSTREAM.items():
                        if tree in pre_u and t.startswith(tree):
                            return f"{pre}{url}{t[len(tree):]}{post}"
                    label = re.sub(r"\[([^\]]*)\]", r"\1", pre).strip()
                    return f"{label} *(not published)*"
            # 2) experiment harness/raw -> that experiment's README
            exp = experiment_of(rel)
            if exp and ("/".join(t.split("/")[-2:]).startswith("harness/") or "harness/" in t or "raw/" in t):
                return f"{pre}/{exp}/README.md{post} *(source private)*"
            return m.group(0)                                       # unknown: let the gate flag it

        text = LINK.sub(repl, text)
        if text != orig:
            p.write_text(text)
            changed += 1
    print(f"rewrite: {changed} published file(s) adjusted")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--staging", default=str(ROOT.parent / "silicon-ledger-public-staging"))
    a = ap.parse_args()
    return rewrite(Path(a.staging))


if __name__ == "__main__":
    sys.exit(main())
