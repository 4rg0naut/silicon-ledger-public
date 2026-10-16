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
  COUNTS    spine counts quoted in WHATSNEW.md / PUBLIC-OPENCLAIMS.md / openclaims README must
            equal counts derived live from the staged claims-*.jsonl (no hand-maintained drift).

usage: python3 tools/publish/check_public.py [--staging PATH]     # default: ../silicon-ledger-public-staging
exit:  0 = clean, 1 = violations (publish must not proceed)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent          # silicon-ledger/
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
STATUS = re.compile(r"\b(NEW|EXT|KNOWN)\b")


def is_exempt(rel: str) -> bool:
    """Pinned third-party material: its links belong to other projects."""
    return "/raw/" in rel


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

# --- case-sensitivity + anchor checks (added 2026-10-10 after a reader-reported dead link) ---------
# macOS volumes are case-INSENSITIVE, so a link to "Results/FOO.md" resolves locally and 404s on
# GitHub. And a link with a "#fragment" only checks the file, not the heading: a fragment that does
# not exist scrolls nowhere. Both are invisible in-tree, so they are checked explicitly here.
ANCHOR_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]*#[^)\s]+)\)")


def slugify(heading: str) -> str:
    h = heading.strip().lstrip("#").strip().lower()
    h = re.sub(r"[^\w\s-]", "", h)
    return re.sub(r"[\s_]+", "-", h).strip("-")


def _case_differs(stage: Path, rel: str) -> str | None:
    """Return the real path when the link's spelling differs in case from disk."""
    p = stage / rel
    if p.exists():
        return None                                     # exact case on disk
    parent = (stage / rel).parent
    if not parent.exists():
        return None
    want = os.path.basename(rel)
    for entry in os.listdir(parent):
        if entry.lower() == want.lower() and entry != want:
            return os.path.join(os.path.relpath(parent, stage), entry)
    return None


def check_case_and_anchors(stage: Path) -> list[str]:
    bad = []
    for p in sorted(stage.rglob("*.md")):
        rel = os.path.relpath(p, stage)
        if "/raw/" in rel:
            continue
        text = p.read_text(errors="replace")
        for target in LINK.findall(text):
            if target.startswith(("http", "mailto:", "#", "tel:")):
                continue
            t = target.split("#")[0].split("?")[0]
            if not t:
                continue
            t = t.lstrip("/") if t.startswith("/") else os.path.normpath(
                os.path.join(os.path.dirname(rel), t)).lstrip("/")
            real = _case_differs(stage, t)
            if real:
                bad.append(f"{rel}: link case differs from disk -> {target} (on disk: {real})")
        # anchors
        for target in ANCHOR_LINK.findall(text):
            t, frag = target.split("#", 1)
            if t.startswith("http") or not t:
                continue
            tgt = stage / (t.lstrip("/") if t.startswith("/") else
                           os.path.normpath(os.path.join(os.path.dirname(rel), t)).lstrip("/"))
            if not tgt.exists() or tgt.suffix != ".md":
                continue
            heads = {slugify(l) for l in tgt.read_text(errors="replace").splitlines() if l.startswith("#")}
            if frag.strip().lower() not in heads:
                bad.append(f"{rel}: anchor does not exist -> {target}")
    return bad

# Absolute-URL blind spot (added 2026-10-10): the gate checked relative links only, so a doc could
# ship a link to the PRIVATE repo - which 404s for every reader (rights, exactly: private = no
# anonymous access). Any absolute link to the private slug is a violation.
PRIVATE_SLUG = "github.com/4rg0naut/silicon-ledger"


def check_private_slug(stage: Path) -> list[str]:
    bad = []
    for p in sorted(stage.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in (".md", ".txt", ".json"):
            continue
        rel = os.path.relpath(p, stage)
        for i, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
            if PRIVATE_SLUG in line and "silicon-ledger-public" not in line and "silicon-ledger-bench" not in line:
                bad.append(f"{rel}:{i}: links the PRIVATE repo (404 for readers) -> {PRIVATE_SLUG}")
    return bad


# Counts gate (added 2026-10-11, review finding: hand-maintained counts in three docs drifted from
# the spine they describe): the truth is derived from the staged claims-*.jsonl, and every doc that
# quotes a count must quote the derived one.
def check_counts(stage: Path) -> list[str]:
    ocl = stage / "knowledge" / "ane" / "openclaims"
    counts = {}
    for key, name in (("claim.emitted", "claims-emitted"),
                      ("claim.verified", "claims-verified"),
                      ("claim.disputed", "claims-disputed")):
        p = ocl / f"{name}.jsonl"
        if not p.exists():
            return [f"openclaims/{name}.jsonl missing from staging"]
        n = 0
        for i, raw in enumerate(p.read_text(errors="replace").splitlines(), 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                if json.loads(raw).get("event_type") == key:
                    n += 1
            except json.JSONDecodeError:
                return [f"openclaims/{name}.jsonl:{i}: unparseable line"]
        counts[key] = n
    e, v, d = counts["claim.emitted"], counts["claim.verified"], counts["claim.disputed"]
    t = e + v + d
    want = [
        ("WHATSNEW.md", f"({e} claims, {t} provenance events"),
        ("PUBLIC-OPENCLAIMS.md", f"**{e} claims emitted**"),
        ("PUBLIC-OPENCLAIMS.md", f"**{v} verification events**"),
        ("PUBLIC-OPENCLAIMS.md", f"**{d} disputed**"),
        ("PUBLIC-OPENCLAIMS.md", f"{t} valid, 0 INVALID (of {t})"),
        ("knowledge/ane/openclaims/README.md", f"**{t} / {t} events validate"),
        ("knowledge/ane/openclaims/README.md", f"{e} `claim.emitted` + {v} `claim.verified` + {d} `claim.disputed`"),
    ]
    bad = []
    for rel, s in want:
        p = stage / rel
        if not p.exists() or s not in p.read_text(errors="replace"):
            bad.append(f"{rel}: stale/missing count string (derived says {t} total / {e} emitted): {s!r}")
    return bad


# --- machine-identity gate (added 2026-10-16, owner request) --------------------------------------
# The owner's machine/volume names are attack surface: they leak a disk-naming convention that ties
# published material to a real fleet. Scrubbing must hold on EVERY publication, not once when a
# label is first noticed. Two layers:
#   (a) structural: any /Volumes/<name> in the published tree must be the neutral /Volumes/data.
#       macOS system volumes under /System/Volumes/ (e.g. /System/Volumes/Preboot) are Apple paths,
#       not owner naming, and are exempt.
#   (b) denylist: known personal labels that must never reappear; extend when a label is retired.
VOLUME_RE = re.compile(r"/Volumes/([^\s\"/`)\]]*)")
VOLUME_OK = {"data", "…"}
SYSTEM_PREFIX = "/System"
MACHINE_LABELS = ("<volume>", "<volume>", "/Volumes/data", "/Volumes/data", "/Volumes/data",
                  "/Volumes/data", "<host>", "<volume>/")


def check_machine_names(stage: Path) -> list[str]:
    bad = []
    for p in sorted(stage.rglob("*")):
        if not p.is_file():
            continue
        rel = os.path.relpath(p, stage)
        if rel == os.path.join("tools", "publish", "check_public.py"):
            continue                           # this gate quotes sample paths and its own regex
        data = p.read_bytes()
        if b"\x00" in data:                    # binary: publish.sh does not scrub it either
            continue
        text = data.decode("utf-8", errors="replace")
        for m in VOLUME_RE.finditer(text):
            if m.group(1).rstrip(".,;:!?") in VOLUME_OK:
                continue
            if text[max(0, m.start() - len(SYSTEM_PREFIX)):m.start()] == SYSTEM_PREFIX:
                continue
            bad.append(f"{rel}: owner volume path -> {m.group(0)}")
        for label in MACHINE_LABELS:
            if label in text:
                bad.append(f"{rel}: personal machine label -> {label!r}")
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
    case_anchor = check_case_and_anchors(stage)
    priv = check_private_slug(stage)
    counts = check_counts(stage)
    machine = check_machine_names(stage)
    for label, bad in (("LINKS", links), ("NOVELTY", novelty), ("CASE/ANCHORS", case_anchor),
                       ("PRIVATE-SLUG", priv), ("COUNTS", counts), ("MACHINE-NAMES", machine)):
        if bad:
            print(f"FAIL {label}: {len(bad)} violation(s)")
            for b in bad[:15]:
                print(f"  {b}")
            if len(bad) > 15:
                print(f"  … {len(bad) - 15} more")
        else:
            print(f"OK   {label}")
    return 1 if (links or novelty or case_anchor or priv or counts or machine) else 0


if __name__ == "__main__":
    sys.exit(main())
