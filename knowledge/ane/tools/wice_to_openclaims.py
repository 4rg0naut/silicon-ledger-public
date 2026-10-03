#!/usr/bin/env python3
"""Convert WiCE into OpenClaims events.

WiCE: "Real-World Entailment for Claims in Wikipedia" (EMNLP 2023). ~2,000 Wikipedia sentences, each
with the web article it cites, an entailment label, the sentences that support it, and the claim
tokens that are not supported.

Three things about this dataset decide the conversion, and getting any of them wrong would corrupt
the gold silently:

1. **It is an ENTAILMENT dataset.** `not_supported` means *not entailed* -- NOT *contradicted*. A
   claim can fail to be supported because the source says the opposite, OR because the source is
   silent. Mapping it to `contradicts` would manufacture contradictions that nobody annotated.
   It maps to `verification_result: inconclusive` with evidence `support_type: context_only` --
   the source is cited, it simply does not establish the claim.

2. **The same claim appears ~3 times**, each with a different evidence chunk, because different
   annotators picked different supporting sentences. The published evaluation protocol is to take
   **the maximum entailment score over all chunks per claim**. We keep the rows separate so that
   protocol stays expressible -- one `claim.emitted` per claim, one evidence + verification per chunk.

3. **`supporting_sentences` is a list of ALTERNATIVE valid sets** (`[[5,15],[15,17]]` -- both are
   correct). The oracle files expose one set per row as `meta.oracle_idx`, so we use that and record
   the alternative count as a facet.

usage: python tools/wice_to_openclaims.py
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
from pathlib import Path

import openclaims as oc

REPO = Path(__file__).resolve().parents[3]
# WICE oracle data is not committed (data/ lives outside the repo; historical
# home was /Volumes/data/local_ai_stack/data/wice/). Override with WICE_SRC.
SRC = Path(os.environ.get("WICE_SRC", str(REPO / "data" / "wice" / "oracle_subclaim_test.jsonl")))
OUT = Path(__file__).resolve().parent.parent / "openclaims"
NOW = "2026-09-24T09:00:00Z"
SCHEMA_URL = "https://openclaims.org/schemas/openclaims/0.1/ClaimEvent.schema.json"

# label -> evidence support_type. The `not_supported` row is the one that matters.
SUPPORT = {
    "supported": "supports_directly",
    "partially_supported": "supports_partially",
    "not_supported": "context_only",          # NOT "contradicts" -- see the docstring
}
# label -> verification_result. The spine has no "partial"; that nuance lives in support_type.
RESULT = {
    "supported": "supported",
    "partially_supported": "supported",
    "not_supported": "inconclusive",
}

ANNOTATOR = {"agent_id": "urn:agent:wice-annotators", "agent_type": "human",
             "name": "WiCE annotators (Kamoi et al., EMNLP 2023)"}
IMPORTER = {"agent_id": "urn:service:wice-importer", "agent_type": "service",
            "name": "WiCE -> OpenClaims importer"}


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(b).digest()).decode().rstrip("=")


def join(evidence: list[str]) -> tuple[str, list[tuple[int, int]]]:
    """Join the evidence sentences, returning the text and each sentence's char range."""
    text, spans, pos = [], [], 0
    for s in evidence:
        text.append(s)
        spans.append((pos, pos + len(s)))
        pos += len(s) + 1
    return "\n".join(text), spans


def span_for(idx: list[int], spans: list[tuple[int, int]], whole: tuple[int, int]) -> dict:
    """A text_span covering the cited sentences; the whole chunk when nothing is cited."""
    got = [spans[i] for i in idx if 0 <= i < len(spans)]
    if not got:
        return {"type": "text_span", "start": whole[0], "end": whole[1]}
    return {"type": "text_span", "start": min(a for a, _ in got), "end": max(b for _, b in got)}


def complete(ev: dict) -> dict:
    """Fill every field ClaimEvent declares -- an incomplete event digests differently than it
    validates, which we found the hard way."""
    for k, v in {"claim_ref": None, "sources": [], "evidence": [], "contradicting_evidence": [],
                 "tool_runs": [], "inferences": [], "verification": None, "dispute_rationale": None,
                 "retracted_at": None, "retraction_reason": None, "original_event_ref": None,
                 "auditable_trace": None}.items():
        ev.setdefault(k, v)
    return ev


def main():
    OUT.mkdir(exist_ok=True)
    if not SRC.exists():
        sys.exit(f"missing WICE oracle input: {SRC}\n"
                 "Set WICE_SRC to a copy of oracle_subclaim_test.jsonl (not committed; data/).")
    rows = [json.loads(l) for l in open(SRC) if l.strip()]
    print(f"  oracle rows: {len(rows)}")

    emitted: dict[str, dict] = {}
    verified: list[dict] = []
    no_citation = 0

    for i, r in enumerate(rows):
        cid_raw = r["meta"]["id"]                     # e.g. test00561-0  (claim id incl. subclaim)
        claim_id = f"clm_wice_{cid_raw}"
        source_id = f"src_wice_{cid_raw}"
        text, spans = join(r["evidence"])
        whole = (spans[0][0], spans[-1][1]) if spans else (0, 0)
        oracle = r["meta"].get("oracle_idx") or []
        if not oracle:
            no_citation += 1
        selector = span_for(oracle, spans, whole)

        if claim_id not in emitted:
            emitted[claim_id] = complete({
                "event_type": "claim.emitted", "event_time": NOW, "spec_version": "0.1.0",
                "schema_url": SCHEMA_URL, "producer": IMPORTER,
                "claim": {"claim_id": claim_id, "text": r["claim"], "claim_type": "factual",
                          "asserted_at": NOW, "derived_from_claims": [], "relations": [],
                          "context": {"wikipedia_title": r["meta"].get("claim_title"),
                                      "wikipedia_section": r["meta"].get("claim_section")},
                          "facets": {"wice": {
                              "_producer": "silicon-ledger",
                              "_schemaURL": "https://raw.githubusercontent.com/4rg0naut/silicon-ledger/main/schemas/facets/silicon-ledger/1.json",
                              "meta_id": cid_raw, "dataset": "WiCE oracle_chunks/subclaim/test",
                              "licence": "CC BY-SA 4.0"}}},
                "sources": [{"source_id": source_id,
                             "uri": f"wice://oracle_chunk/{cid_raw}",
                             "version": f"chunk_{i}",
                             "retrieved_at": NOW, "license": "CC BY-SA 4.0",
                             "digest": {"algorithm": "sha256", "encoding": "base64url",
                                        "value": b64(text.encode())}}],
                "evidence": [{"evidence_id": f"ev_wice_{cid_raw}_{i}", "source_ref": source_id,
                              "claim_ref": claim_id, "selector": selector,
                              "support_type": SUPPORT[r["label"]]}],
                "tool_runs": [{"tool_run_id": f"run_wice_{i}", "tool_type": "import",
                               "tool": {"name": "wice_to_openclaims",
                                        "provider": "local"}}],
                "event_id": f"evt_wice_{cid_raw}_emitted",
            })

        verified.append(complete({
            "event_type": "claim.verified", "event_time": NOW, "spec_version": "0.1.0",
            "schema_url": SCHEMA_URL, "producer": ANNOTATOR, "claim_ref": claim_id,
            "verification": {
                "verification_id": f"ver_wice_{cid_raw}_{i}",
                "verification_result": RESULT[r["label"]],
                "verification_method": "human_review",
                "claim_status": "active", "validator": ANNOTATOR, "verified_at": NOW},
            "evidence": [{"evidence_id": f"ev_wice_v_{cid_raw}_{i}", "source_ref": source_id,
                          "claim_ref": claim_id, "selector": selector,
                          "support_type": SUPPORT[r["label"]]}],
            "event_id": f"evt_wice_{cid_raw}_verified_{i}",
        }))

    # validate every event against the real schema, and digest the complete form
    valid = invalid = 0
    for ev in list(emitted.values()) + verified:
        try:
            oc.validate_event(oc.with_event_digest(complete(dict(ev)))); valid += 1
        except Exception as e:
            invalid += 1
            if invalid <= 3:
                print(f"    INVALID {ev.get('event_id')}: {type(e).__name__}: {str(e)[:150]}")

    for name, rows_ in (("wice-emitted", list(emitted.values())), ("wice-verified", verified)):
        with open(OUT / f"{name}.jsonl", "w") as f:
            for r in rows_:
                f.write(json.dumps(oc.with_event_digest(complete(dict(r)))) + "\n")

    import collections
    print(f"  claim.emitted  : {len(emitted)}  (one per distinct claim)")
    print(f"  claim.verified : {len(verified)}  (one per evidence chunk)")
    print(f"  rows with no cited sentence: {no_citation}")
    print(f"  labels: {dict(collections.Counter(r['label'] for r in rows))}")
    print(f"\n  schema validation: {valid} valid, {invalid} INVALID")
    print(f"  wrote {OUT}/wice-*.jsonl")
    return 1 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(main())