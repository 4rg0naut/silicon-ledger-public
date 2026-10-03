#!/usr/bin/env python3
"""Convert our knowledge base into OpenClaims events.

The proof that the spine holds our data. Maps:

  554 records            ->  claim.emitted  (Claim + Source + ToolRun)
  55 agent verdicts      ->  claim.verified (verification_method: model_check)
  53 Von verdicts        ->  claim.verified (verification_method: model_check)
  17 contested records   ->  claim.disputed + a ClaimRelation

Three mappings are worth stating explicitly, because they are where the spine earns its place:

1. `support_type` IS our verdict space. yes -> supports_directly,
   partial -> supports_partially, no -> contradicts. Nothing to translate.

2. A model's verdict and a human's verdict are the SAME shape but a different
   `verification_method` and a different `validator.agent_type`. They sit side by side and neither
   overwrites the other. The hand labels become the first entries in a permanent history rather than
   a one-off test set.

3. Evidence becomes a POINTER, not a copy. We recompute where the passage sits inside the digest-
   pinned cached source and emit a real `text_span`. Anyone can re-derive it and check it has not
   drifted, which a copied slab of text can never offer.

Our `confidence` label (measured/documented/inferred/claimed) is NOT a spine concept and is retired
into a facet. It recorded how a claim was established, not who checked it -- and we measured that it
carried no signal about quality anyway.

usage (from the repo root): python3 -m venv .venv
        .venv/bin/pip install "git+https://github.com/openclaims-ai/openclaims.git#subdirectory=python"
        .venv/bin/python knowledge/ane/tools/to_openclaims.py            # write events, validate each one
        .venv/bin/python knowledge/ane/tools/to_openclaims.py --check   # validate the committed events only

  The SDK is not on PyPI (as of 2026-10-03): install it from the upstream
  repo `subdirectory=python` as above. Pure `python3` (system) runs every
  other bench script; only this tool needs the SDK venv.

Reproducibility from a fresh clone:
  The verdict inputs (evaluation/verify/testset.jsonl,
  evaluation/decision/von_per_item.json) are IN the repo, so the claim/verdict
  structure reproduces anywhere. What does NOT reproduce from a fresh clone is
  the digest-pinning: the cached source copies under knowledge/ane/grounding/cache/
  are gitignored (we keep POINTERS, not copies — see .gitignore). Without the
  cache, `cached_text()` returns None for every source, so no digest is pinned
  and no text_span is located (all verdict evidence comes out `unlocatable`).
  The committed openclaims/claims-*.jsonl are therefore CANONICAL as emitted
  (with cache present); `--check` validates those committed events against the
  schema without needing the cache. Do not regenerate and commit over them from
  a cache-less clone.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # knowledge/ane
REPO = ROOT.parent.parent                              # repository root
CASES = REPO / "evaluation" / "verify" / "testset.jsonl"
VON = REPO / "evaluation" / "decision" / "von_per_item.json"
GROUND = ROOT / "grounding" / "cache"
OUT = ROOT / "openclaims"
NOW = "2026-09-23T12:00:00Z"

import openclaims as oc

SCHEMA_URL = "https://openclaims.org/schemas/openclaims/0.1/ClaimEvent.schema.json"

# --- id helpers: deterministic, so re-running the converter does not churn ids ---------
def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", s)

def cid(rec_id):   return f"clm_{_slug(rec_id)}"
def sid(src):      return "src_" + _slug(hashlib.sha256(src.encode()).hexdigest()[:20])
def eid(rec_id, n): return f"ev_{_slug(rec_id)}_{n}"

# our kind -> the spine's coarser claim_type; the fine kind is preserved in a facet
CTYPE = {
    "fact": "factual", "gotcha": "factual", "measurement": "factual",
    "definition": "factual", "procedure": "factual",
    "open-question": "prediction",
}
# our verdict -> the spine's support_type
SUPPORT = {
    "yes": "supports_directly",
    "partial": "supports_partially",
    "no": "contradicts",
    "insufficient": "context_only",
}
# our verdict -> the spine's verification_result
RESULT = {
    "yes": "supported", "partial": "supported",
    "no": "contradicted", "insufficient": "inconclusive",
}

WRITER = {"agent_id": "urn:agent:kb-writing-assistant", "agent_type": "model",
          "name": "Knowledge-base writing agents"}
# The 55 verdicts were produced by an AI agent reading each claim against its passage. That is
# model review. Labelling it human_review would be false provenance, which in a project built on
# provenance is the worst available bug -- so the honest label is model_check and agent_type model.
# If a human later reviews any of these, that is a NEW, separate verification event.
REVIEWER = {"agent_id": "urn:agent:silicon-ledger-claim-reviewer", "agent_type": "model",
            "name": "AI agent (claim read against its cited passage)"}
VON_AGENT = {"agent_id": "urn:model:von-1.0", "agent_type": "model", "name": "Von-1.0 (ModernBERT-Large NLI)"}


def b64url_sha(b: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(b).digest()).decode().rstrip("=")


def cached_text(source: str) -> str | None:
    """Our cached copy of a source, keyed by the same hash kb_ground.py uses."""
    for ver in ("v2-", ""):
        p = GROUND / (ver + hashlib.sha256(source.encode()).hexdigest()[:24] + ".txt")
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
    return None


def text_span(source: str, passage: str) -> dict | None:
    """Locate the passage inside the digest-pinned cached source.

    A pointer into a specific copy is meaningful; a copied slab is not.
    """
    txt = cached_text(source)
    if not txt:
        return None
    probe = passage.strip()[:300]
    i = txt.find(probe)
    if i < 0:
        probe = probe[:120]
        i = txt.find(probe)
        if i < 0:
            return None
    return {"type": "text_span", "start": i, "end": i + len(probe)}


def load_records():
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
                    r.setdefault("split", "train")
                    r["_file"] = p.name
                    recs.append(r)
    return recs


def complete(ev: dict) -> dict:
    """Fill every field ClaimEvent declares.

    The SDK digests the payload as the model would normalise it, so an event that omits optional
    fields produces a digest over a *different* payload than the one validation hashes -- the digest
    then verifies against our own bytes but fails `validate_event`. Emitting the full field set
    makes the two agree. Found by validating rather than assuming.
    """
    for k, v in {"claim_ref": None, "sources": [], "evidence": [],
                 "contradicting_evidence": [], "tool_runs": [], "inferences": [],
                 "verification": None, "dispute_rationale": None, "retracted_at": None,
                 "retraction_reason": None, "original_event_ref": None,
                 "auditable_trace": None}.items():
        ev.setdefault(k, v)
    return ev


def assert_no_human_review(events):
    """There is no code path to human_review, and this enforces it.

    A cBLAS/torch comparison IS verification -- but it is MACHINE verification, and a machine may
    not sign a human's name. An earlier revision of this converter labelled 55 agent-produced
    verdicts human_review; the label was false, in a project whose entire purpose is provenance
    that is worse than a wrong number. human_review may appear only as a NEW, separately emitted
    verification written by a human-attested pass. The tool must be unable to write it.
    """
    bad = [e["event_id"] for e in events
           if (e.get("verification") or {}).get("verification_method") == "human_review"]
    if bad:
        raise AssertionError(f"converter emitted human_review for {bad[:3]} -- no code path may do this")


def check_committed() -> int:
    """Validate the committed claim events against the schema, cache-free.

    The committed files are canonical (emitted with the grounding cache
    present). This confirms the schema still accepts every committed event —
    digest, fields, facet shape — so the corpus stays machine-verifiable from a
    fresh clone that does not have the gitignored cache.
    """
    import openclaims as oc
    total = valid = invalid = 0
    for name in ("claims-emitted", "claims-verified", "claims-disputed"):
        p = OUT / f"{name}.jsonl"
        if not p.exists():
            print(f"    MISSING {p}")
            return 1
        for line in p.read_text().splitlines():
            if not line.strip():
                continue
            total += 1
            try:
                oc.validate_event(json.loads(line))
                valid += 1
            except Exception as e:
                invalid += 1
                if invalid <= 3:
                    print(f"    INVALID {name}: {type(e).__name__}: {str(e)[:160]}")
    print(f"  committed events : {valid} valid, {invalid} INVALID (of {total})")
    return 1 if invalid else 0


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="validate the committed openclaims/claims-*.jsonl against the "
                         "schema (no grounding cache or verdict inputs needed)")
    args = ap.parse_args()

    if args.check:
        return check_committed()

    OUT.mkdir(exist_ok=True)
    if not CASES.exists():
        raise SystemExit(f"missing verdict input {CASES} — expected in the repo at "
                         f"evaluation/verify/testset.jsonl")
    recs = load_records()
    cases = {json.loads(l)["id"]: json.loads(l) for l in open(CASES)}
    von = {r["id"]: r for r in json.load(open(VON))} if VON.exists() else {}

    emitted, verified, disputed = [], [], []
    no_selector = 0
    valid = invalid = 0

    for r in recs:
        src = r.get("source", "")
        src_id = sid(src)
        # NOTE: evidence_status is deliberately ABSENT when the evidence verifies. The schema
        # declares default "ok", and the bench schema uses the same convention ("ok, default;
        # absent = ok"). A record therefore only says something when something is wrong. Do not
        # "fix" this by writing an explicit "ok": it would add a field to 528 records that carries
        # no information, and it would diverge from the other producer's convention.
        facet = {"_producer": "silicon-ledger", "_schemaURL": "https://raw.githubusercontent.com/4rg0naut/silicon-ledger/main/schemas/facets/silicon-ledger/1.json",
                 "kind": r.get("kind"), "legacy_confidence": r.get("confidence"),
                 "topic": r.get("topic", []), "entities": r.get("entities", []),
                 "split": r.get("split")}
        if r.get("caveat"):
            facet["caveat"] = r["caveat"]

        ev = {
            "event_type": "claim.emitted",
            "event_time": NOW,
            "spec_version": "0.1.0",
            "schema_url": SCHEMA_URL,
            "producer": WRITER,
            "claim": {
                "claim_id": cid(r["id"]), "text": r["claim"],
                "claim_type": CTYPE.get(r.get("kind"), "factual"),
                "asserted_at": NOW, "derived_from_claims": [], "relations": [],
                "facets": {"silicon-ledger": facet},
            },
            "sources": [{"source_id": src_id, "uri": src,
                         "retrieved_at": NOW, "license": r.get("license", "see SOURCES.md")}],
            "evidence": [],
            "tool_runs": [{"tool_run_id": f"run_{_slug(r['id'])}", "tool_type": "knowledge_capture",
                           "tool": {"name": "kb-writing-agent", "provider": "local"}}],
            "event_id": f"evt_{_slug(r['id'])}_emitted",
        }
        # pin the source with a digest when we hold a copy
        txt = cached_text(src)
        if txt is not None:
            ev["sources"][0]["digest"] = {"algorithm": "sha256", "encoding": "base64url",
                                          "value": b64url_sha(txt.encode())}

        # verdict on support, produced by an AI agent reading the claim against its passage.
        c = cases.get(r["id"])
        if c and c.get("gold"):
            span = text_span(src, c.get("passage", ""))
            # An unlocatable span is REJECTED, not patched. Emitting a degenerate {0,0} pointer is a
            # fabrication: it asserts evidence at the top of the file regardless of content, and it
            # validates. Luvia-AB/openclaims rejects a span not found verbatim in the registered
            # text, at write time, in non-LLM code -- this is that rule. No evidence is better than
            # evidence that is wrong.
            evidence = []
            if span is None:
                no_selector += 1
                ev["claim"]["facets"]["silicon-ledger"]["evidence_status"] = "unlocatable"
            else:
                evidence = [{"evidence_id": eid(r["id"], 1), "source_ref": src_id,
                             "claim_ref": cid(r["id"]), "selector": span,
                             "support_type": SUPPORT[c["gold"]]}]
            v = {"event_type": "claim.verified", "event_time": NOW, "spec_version": "0.1.0",
                 "schema_url": SCHEMA_URL,
                 "producer": REVIEWER, "claim_ref": cid(r["id"]),
                 "verification": {"verification_id": f"ver_{_slug(r['id'])}_review",
                                  "verification_result": RESULT[c["gold"]],
                                  "verification_method": "model_check",
                                  "claim_status": "active", "validator": REVIEWER,
                                  "verified_at": NOW},
                 "evidence": evidence,
                 "event_id": f"evt_{_slug(r['id'])}_review"}
            verified.append(v)

        # Von's model verdict -> model_check, sits BESIDE the human one
        if r["id"] in von:
            v2 = {"event_type": "claim.verified", "event_time": NOW, "spec_version": "0.1.0",
                  "schema_url": SCHEMA_URL,
                  "producer": VON_AGENT, "claim_ref": cid(r["id"]),
                  "verification": {"verification_id": f"ver_{_slug(r['id'])}_von",
                                   "verification_result": RESULT.get(
                                       {"yes": "yes", "partial": "partial", "no": "no"}.get(von[r["id"]]["pred"], "partial"),
                                       "inconclusive"),
                                   "verification_method": "model_check",
                                   "claim_status": "active", "validator": VON_AGENT,
                                   "verified_at": NOW},
"evidence": [],
                  "event_id": f"evt_{_slug(r['id'])}_von"}
            # OpenClaims v0.1 interop bug, isolated by test: a Python float 1.0 serialises as
            # "1.0" and the JS canonicaliser writes "1", so the SDKs compute DIFFERENT digests for
            # the same event. Emitting int 1 fixes the JS side and breaks the Python side -- the two
            # are mutually incompatible for this value. Omitting it when it is exactly 1.0 is the
            # only form BOTH accept, and a model claiming certainty loses nothing measurable.
            if von[r["id"]]["conf"] != 1.0:
                v2["verification"]["confidence"] = von[r["id"]]["conf"]
            verified.append(v2)

        emitted.append(ev)
        if r.get("contested"):
            disputed.append({"event_type": "claim.disputed", "event_time": NOW,
                             "spec_version": "0.1.0", "schema_url": SCHEMA_URL,
                             "producer": REVIEWER,
                             "claim_ref": cid(r["id"]),
                             "dispute_rationale": "Sources disagree; both positions recorded in the record.",
                             "evidence": [],
                             "event_id": f"evt_{_slug(r['id'])}_disputed"})

    # validate every event against the real schema
    assert_no_human_review(verified)

    for ev in emitted + verified + disputed:
        try:
            ev2 = oc.with_event_digest(complete(dict(ev)))
            oc.validate_event(ev2)
            valid += 1
        except Exception as e:
            invalid += 1
            if invalid <= 3:
                print(f"    INVALID {ev.get('event_id')}: {type(e).__name__}: {str(e)[:160]}")

    for name, rows in (("claims-emitted", emitted), ("claims-verified", verified),
                       ("claims-disputed", disputed)):
        with open(OUT / f"{name}.jsonl", "w") as f:
            for r in rows:
                f.write(json.dumps(oc.with_event_digest(complete(dict(r)))) + "\n")

    print(f"  records        : {len(recs)}")
    print(f"  claim.emitted  : {len(emitted)}")
    print(f"  claim.verified : {len(verified)}  "
          f"({len([v for v in verified if v['verification']['verification_method']=='model_check'])} model_check, "
          f"{len([v for v in verified if v['verification']['verification_method']=='human_review'])} human_review)")
    print(f"  claim.disputed : {len(disputed)}")
    print(f"  text_span located: {len(emitted)-no_selector if False else 'see below'}")
    print(f"  spans not located: {no_selector}")
    print(f"\n  schema validation: {valid} valid, {invalid} INVALID")
    print(f"  wrote {OUT}/")
    return 1 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())