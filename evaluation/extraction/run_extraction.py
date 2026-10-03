#!/usr/bin/env python3
"""Extraction layer test — does it find the technical facts, and does label wording matter?

The trap this avoids: a claim is a PROPOSITION, while GLiNER2.5 returns SPANS and triples. Scoring
"passage -> our claims" directly is a category error and would rank the model on the wrong thing.

Instead the gold is derived mechanically and defensibly:

    gold(claim, passage) = the technical tokens that appear in BOTH

If a passage and the claim drawn from it both contain `_ANEModel`, `0x07fff` or `TileDMASrc`, then a
competent extractor given a suitable schema should surface it. This needs no per-record hand work and
cannot be gamed by either side.

The second axis is the one that nearly produced a false negative on a working tool: GLiNER is
zero-shot but sensitive to LABEL WORDING. So each concept is probed with several phrasings and the
best is reported, not the first.
"""

from __future__ import annotations

import json
import re
import time
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERIFY = HERE.parent / "verify" / "testset.jsonl"

# a technical token worth extracting: private API names, hex, identifiers, chips, files
TECH = re.compile(r"""
    (?P<api>_[A-Z][A-Za-z0-9]{2,})          # _ANEModel, _ANEInMemoryModel
  | (?P<hex>0x[0-9a-fA-F]{2,})              # 0x07fff
  | (?P<chip>\b[AM]\d{1,2}\b)               # M3, A11
  | (?P<camel>\b[A-Z][a-z]+[A-Z][A-Za-z0-9]+\b)   # TileDMASrc, KernelDMASrc
  | (?P<file>\b[A-Za-z0-9_\-]+\.(?:m|mm|h|c|cpp|py|swift|json|md)\b)
  | (?P<fn>\b[a-z_][a-z0-9_]{3,}_[a-z0-9_]+\b)    # snake_case functions
""", re.X)

# several phrasings per concept — the whole point of the experiment
PHRASINGS = {
    "technical identifier": ["technical identifier", "code identifier", "symbol name"],
    "API name":             ["API name", "private API", "framework class", "method selector"],
    "value":                ["numeric value", "hexadecimal value", "measurement"],
    "hardware":             ["chip", "hardware component", "processor"],
}


def gold_terms(claim: str, passage: str) -> set[str]:
    """Technical tokens present in BOTH the claim and its passage."""
    c = {m.group(0) for m in TECH.finditer(claim)}
    p = {m.group(0) for m in TECH.finditer(passage)}
    return c & p


def main():
    items = [json.loads(l) for l in open(VERIFY)]
    usable = []
    for t in items:
        g = gold_terms(t["claim"], t["passage"])
        if g:
            usable.append({**t, "gold": sorted(g)})
    print(f"  items with derivable gold: {len(usable)} / {len(items)}")
    n = 20
    sample = usable[:n]
    print(f"  testing on {len(sample)}")
    print(f"  mean gold terms/item: {statistics.mean(len(s['gold']) for s in sample):.1f}")

    from gliner2 import BoundaryExtractor
    m = BoundaryExtractor.from_pretrained("fastino/gliner2.5-small-v1")

    results = {}
    for concept, phrasings in PHRASINGS.items():
        for ph in phrasings:
            rec_all, lat_all, found_all = [], [], []
            for s in sample:
                t0 = time.perf_counter()
                try:
                    out = m.extract(s["passage"], {"entities": [ph]}, include_confidence=True)
                except Exception as e:
                    print(f"  {ph!r}: FAILED {type(e).__name__}")
                    out = {}
                lat_all.append((time.perf_counter() - t0) * 1000)
                spans = []
                ents = (out or {}).get("entities", {})
                for v in ents.values():
                    if isinstance(v, list):
                        spans += [x.get("text", "") for x in v if isinstance(x, dict)]
                got = {g for g in s["gold"] if any(g in sp or sp in g for sp in spans)}
                rec_all.append(len(got) / max(1, len(s["gold"])))
                found_all.append(len(spans))
            results[(concept, ph)] = {
                "recall": statistics.mean(rec_all),
                "spans_per_item": statistics.mean(found_all),
                "ms": statistics.median(lat_all),
            }

    print(f"\n  {'concept':22} {'phrasing':26} {'recall':>7} {'spans':>6} {'ms':>7}")
    print("  " + "-" * 72)
    best_per_concept = {}
    for (concept, ph), r in results.items():
        print(f"  {concept:22} {ph:26} {r['recall']:7.3f} {r['spans_per_item']:6.1f} {r['ms']:7.1f}")
        if concept not in best_per_concept or r["recall"] > best_per_concept[concept][1]["recall"]:
            best_per_concept[concept] = (ph, r)

    print(f"\n  === best phrasing per concept ===")
    for concept, (ph, r) in best_per_concept.items():
        worst = min((v["recall"] for k, v in results.items() if k[0] == concept))
        print(f"    {concept:22} {ph!r:26} recall {r['recall']:.3f}  "
              f"(worst phrasing {worst:.3f} -> spread {r['recall']-worst:+.3f})")

    spread = [r["recall"] for r in results.values()]
    print(f"\n  recall across ALL phrasings: min {min(spread):.3f}  max {max(spread):.3f}")
    print(f"  => label wording moves the result by {max(spread)-min(spread):.3f} recall")

    (HERE / "results.json").write_text(json.dumps(
        {f"{k[0]}|{k[1]}": v for k, v in results.items()}, indent=2))
    print(f"\n  wrote {HERE/'results.json'}")


if __name__ == "__main__":
    main()