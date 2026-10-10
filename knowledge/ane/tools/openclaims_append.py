#!/usr/bin/env python3
"""openclaims_append.py — extend the OpenClaims spine with records added since the
last full conversion, WITHOUT regenerating the canonical files.

Why not `to_openclaims.py`? That tool regenerates claims-{emitted,verified,disputed}
wholesale and needs the gitignored grounding cache to pin source digests / locate
text spans. On a cache-less clone, regenerating would silently drop the pinned
digests and spans that the committed events already carry. So: never regenerate
here; append.

What it does: load the current records (`knowledge/ane/*.md` fenced ```jsonl), find
those whose claim_id is not already in claims-emitted.jsonl, build the same
claim.emitted event `to_openclaims.py` builds (identical field set via `complete`),
digest it with the SDK, validate it, and append. New `contested` records get a
claim.disputed too. Existing lines are preserved byte-for-byte.

Requires the openclaims SDK venv (`.venv`). usage:
  .venv/bin/python knowledge/ane/tools/openclaims_append.py            # append + validate
  .venv/bin/python knowledge/ane/tools/openclaims_append.py --dry-run  # report only
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import to_openclaims as T  # noqa: E402
import openclaims as oc    # noqa: E402


def load_emitted():
    p = T.OUT / "claims-emitted.jsonl"
    rows = [json.loads(l) for l in open(p) if l.strip()]
    return rows, {r["claim"]["claim_id"] for r in rows}


def emitted_event(r: dict) -> dict:
    """Mirror to_openclaims.py's per-record claim.emitted construction exactly."""
    src = r.get("source", "")
    facet = {"_producer": "silicon-ledger",
             "_schemaURL": "https://raw.githubusercontent.com/4rg0naut/silicon-ledger/main/"
                           "schemas/facets/silicon-ledger/1.json",
             "kind": r.get("kind"), "legacy_confidence": r.get("confidence"),
             "topic": r.get("topic", []), "entities": r.get("entities", []),
             "split": r.get("split", "train")}
    if r.get("caveat"):
        facet["caveat"] = r["caveat"]
    ev = {
        "event_type": "claim.emitted",
        "event_time": T.claimed_at(r),
        "spec_version": "0.1.0",
        "schema_url": T.SCHEMA_URL,
        "producer": T.WRITER,
        "claim": {"claim_id": T.cid(r["id"]), "text": r["claim"],
                  "claim_type": T.CTYPE.get(r.get("kind"), "factual"),
                  "asserted_at": T.claimed_at(r), "derived_from_claims": [],
                  "relations": [], "facets": {"silicon-ledger": facet}},
        "sources": [{"source_id": T.sid(src), "uri": src, "retrieved_at": T.claimed_at(r),
                     "license": r.get("license", "see SOURCES.md")}],
        "evidence": [],
        "tool_runs": [{"tool_run_id": f"run_{T._slug(r['id'])}", "tool_type": "knowledge_capture",
                       "tool": {"name": "kb-writing-agent", "provider": "local"}}],
        "event_id": f"evt_{T._slug(r['id'])}_emitted",
    }
    txt = T.cached_text(src)          # None without the grounding cache -> no source digest
    if txt is not None:
        ev["sources"][0]["digest"] = {"algorithm": "sha256", "encoding": "base64url",
                                      "value": T.b64url_sha(txt.encode())}
    return ev


def disputed_event(r: dict) -> dict:
    return {"event_type": "claim.disputed", "event_time": T.NOW, "spec_version": "0.1.0",
            "schema_url": T.SCHEMA_URL, "producer": T.REVIEWER,
            "claim_ref": T.cid(r["id"]),
            "dispute_rationale": "Sources disagree; both positions recorded in the record.",
            "evidence": [], "event_id": f"evt_{T._slug(r['id'])}_disputed"}


def main(dry=False) -> int:
    rows, have = load_emitted()
    dpath = T.OUT / "claims-disputed.jsonl"
    drows = [json.loads(l) for l in open(dpath) if l.strip()]
    dhave = {r["claim_ref"] for r in drows}

    recs = T.load_records()
    new, new_disputes, invalid = [], [], 0
    for r in recs:
        if T.cid(r["id"]) in have:
            continue
        ev = T.complete(dict(emitted_event(r)))
        try:
            ev = oc.with_event_digest(ev)
            oc.validate_event(ev)
        except Exception as e:
            invalid += 1
            print(f"  INVALID {ev['event_id']}: {type(e).__name__}: {str(e)[:150]}")
            continue
        new.append(ev)
        if r.get("contested") and T.cid(r["id"]) not in dhave:
            dv = oc.with_event_digest(T.complete(dict(disputed_event(r))))
            oc.validate_event(dv)
            new_disputes.append(dv)

    print(f"  records total     : {len(recs)}")
    print(f"  already in spine  : {len(have)}")
    print(f"  new claim.emitted : {len(new)}")
    print(f"  new claim.disputed: {len(new_disputes)}")
    print(f"  invalid           : {invalid}")
    if dry or invalid:
        return 1 if invalid else 0

    with open(T.OUT / "claims-emitted.jsonl", "a") as f:
        for r in new:
            f.write(json.dumps(r) + "\n")
    if new_disputes:
        with open(dpath, "a") as f:
            for r in new_disputes:
                f.write(json.dumps(r) + "\n")
    print(f"  appended to {T.OUT}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(dry="--dry-run" in sys.argv))
