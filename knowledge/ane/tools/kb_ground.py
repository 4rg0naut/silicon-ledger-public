#!/usr/bin/env python3
"""Grounding retriever — put the source text in front of the claim.

No model can validate a claim it cannot see the source for, and a claim like
"the DMA prefetcher throttles at 1 MiB multiples" is meaningless without the paragraph it
came from. This step is pure code on purpose: fetch the source, find the passages that
actually bear on the claim, and write a packet per record. The judgement (does the source
SUPPORT this?) is a separate step, done by a model, and it reads these packets.

    python tools/kb_ground.py --limit 20      # try a sample
    python tools/kb_ground.py                 # all records (cached, resumable)
    python tools/kb_ground.py --report        # resolution summary only

Outputs:
    grounding/cache/        fetched sources, cached by hash
    grounding/packets.jsonl one line per record: claim + top passages + resolution status
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent.parent
CACHE = ROOT / "grounding" / "cache"
PACKETS = ROOT / "grounding" / "packets.jsonl"

UA = "kb-ground/1.0 (+research; contact via repository)"
TIMEOUT = 25
PASSAGE_TARGET = 900          # aim for ~900 char passages
TOP_K = 3

STOP = set("""a an the and or but if then than that this these those of in on at to for from by
with without into over under is are was were be been being do does did have has had it its as not
no nor so such can could may might must shall should will would you your we our they their he she
them there here what which who whom when where why how all any both each few more most other some
only own same too very s t just also""".split())


def tokens(text: str) -> set[str]:
    ws = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    return {w for w in ws if len(w) > 2 and w not in STOP}


CACHE_VERSION = "v2"   # bump when what we fetch changes, so stale cache is ignored


def cache_path(url: str) -> Path:
    return CACHE / (CACHE_VERSION + "-" + hashlib.sha256(url.encode()).hexdigest()[:24] + ".txt")


def gh_raw(url: str) -> str | None:
    """Turn a github.com blob/tree URL into the raw file URL when possible."""
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/(?:blob|raw)/([^/]+)/(.+)", url)
    if m:
        owner, repo, ref, path = m.groups()
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
    return None


def looks_binary(raw: bytes) -> bool:
    """A compiled framework binary is not text. Term-matching decoded bytes is meaningless,
    so such sources must be reported as unvalidatable rather than quietly mis-scored."""
    if not raw:
        return False
    if raw.count(b"\x00") > max(16, len(raw) * 0.005):
        return True
    sample = raw[:4096]
    printable = sum(1 for b in sample if 32 <= b < 127 or b in (9, 10, 13))
    return printable / max(1, len(sample)) < 0.85


def candidates_for(source: str) -> list[str]:
    """Prefer the form of a URL that yields real content rather than a landing page.

    Getting this wrong is invisible: an arXiv /abs/ page returns ~6 KB of abstract, the
    terms do not match, and a perfectly good claim gets judged unsupported. That is a
    retriever bug wearing the costume of a knowledge-base defect.
    """
    out = []
    if gh_raw(source):
        out.append(gh_raw(source))
    m = re.match(r"https?://arxiv\.org/abs/(.+)$", source)
    if m:
        out.append(f"https://arxiv.org/html/{m.group(1)}")
    if re.match(r"https?://github\.com/[^/]+/[^/]+/?$", source):
        # a bare repo URL is a landing page; its README is the only textual content
        out.append(source.replace("github.com", "raw.githubusercontent.com").rstrip("/")
                   + "/HEAD/README.md")
    out.append(source)
    return out


def resolve(source: str) -> tuple[str, str]:
    """Return (status, text). status in {ok, cached, binary, unreachable, empty}."""
    # local paths are free and already on disk
    for prefix in ("/Volumes/data/local_ai_stack", str(REPO), "/"):
        if source.startswith(prefix):
            p = Path(source)
            if not p.exists():
                return "unreachable", ""
            try:
                raw = p.read_bytes()[:4_000_000]
            except Exception as e:
                return "unreachable", f"(read failed: {e})"
            if looks_binary(raw):
                return "binary", "(binary file — text validation not possible)"
            return "ok", raw.decode("utf-8", errors="replace")

    if not source.startswith("http"):
        return "unreachable", f"(unrecognised source shape: {source[:80]})"

    cp = cache_path(source)
    if cp.exists():
        txt = cp.read_text(encoding="utf-8", errors="replace")
        return ("ok" if txt.strip() else "empty"), txt

    last = "no candidate"
    for url in candidates_for(source):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read(4_000_000)
            if looks_binary(raw):
                return "binary", f"(binary at {url})"
            txt = raw.decode("utf-8", errors="replace")
            # strip html crudely; the judge needs words, not markup
            if "<html" in txt[:2000].lower() or "<!doctype" in txt[:2000].lower():
                txt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", txt,
                             flags=re.S | re.I)
                txt = re.sub(r"<[^>]+>", " ", txt)
                txt = re.sub(r"&[a-z]+;", " ", txt)
            txt = re.sub(r"[ \t]+", " ", txt)
            txt = re.sub(r"\n{3,}", "\n\n", txt)
            if not txt.strip():
                last = f"{url}: empty"
                continue
            CACHE.mkdir(parents=True, exist_ok=True)
            cp.write_text(txt, encoding="utf-8")
            return "ok", txt
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
    return "unreachable", f"({last})"


def passages(text: str) -> list[str]:
    """Split into ~PASSAGE_TARGET-char chunks on blank lines, merging short ones."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text)]
    out, buf = [], ""
    for p in paras:
        if not p:
            continue
        if len(buf) + len(p) + 2 <= PASSAGE_TARGET:
            buf = (buf + "\n\n" + p) if buf else p
        else:
            if buf:
                out.append(buf)
            buf = p if len(p) <= PASSAGE_TARGET * 2 else p[:PASSAGE_TARGET * 2]
    if buf:
        out.append(buf)
    return out


def rank(claim: str, text: str) -> list[tuple[float, str]]:
    ct = tokens(claim)
    if not ct:
        return []
    scored = []
    for p in passages(text):
        pt = tokens(p)
        if not pt:
            continue
        overlap = ct & pt
        if not overlap:
            continue
        # coverage of the claim's content words, mildly punished for very long passages
        s = len(overlap) / (len(ct) ** 0.5) / (1 + len(p) / 4000)
        scored.append((s, p))
    scored.sort(key=lambda x: -x[0])
    return scored[:TOP_K]


def load_records() -> list[dict]:
    recs, seen = [], set()
    for p in sorted(ROOT.glob("*.md")):
        for b in re.findall(r"```jsonl\n(.*?)```", p.read_text(encoding="utf-8"), re.S):
            for line in b.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("id") and r["id"] not in seen:
                    seen.add(r["id"])
                    r["_file"] = p.name
                    recs.append(r)
    return recs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--only-file", default=None, help="restrict to one source file")
    args = ap.parse_args()

    recs = load_records()
    if args.only_file:
        recs = [r for r in recs if r["_file"] == args.only_file]
    if args.limit:
        recs = recs[:args.limit]

    print(f"  records to ground: {len(recs)}")
    if args.report:
        return 0

    CACHE.mkdir(parents=True, exist_ok=True)
    counts = {"ok": 0, "empty": 0, "unreachable": 0}
    no_passage = 0
    packets = []
    by_source: dict[str, tuple[str, str]] = {}

    for i, r in enumerate(recs, 1):
        src = r.get("source", "")
        if src not in by_source:
            by_source[src] = resolve(src)
        status, text = by_source[src]
        counts[status] = counts.get(status, 0) + 1
        hits = rank(r.get("claim", ""), text) if status == "ok" else []
        if status == "ok" and not hits:
            no_passage += 1
        packets.append({
            "id": r["id"],
            "claim": r["claim"],
            "kind": r.get("kind"),
            "confidence": r.get("confidence"),
            "source": src,
            "source_type": r.get("source_type"),
            "resolution": status,
            "passages": [p for _, p in hits],
            "scores": [round(s, 4) for s, _ in hits],
        })
        if i % 50 == 0:
            print(f"    {i}/{len(recs)} ...", flush=True)

    with PACKETS.open("w", encoding="utf-8") as f:
        for p in packets:
            f.write(json.dumps(p) + "\n")

    print("\n=== resolution ===")
    total = sum(counts.values()) or 1
    for k in sorted(counts, key=lambda x: -counts[x]):
        print(f"  {k:12} {counts[k]:4}  ({100*counts[k]/total:.1f}%)")
    print(f"  distinct sources fetched: {len(by_source)}")
    print(f"  records with NO matching passage: {no_passage}")
    print(f"\n  wrote {PACKETS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())