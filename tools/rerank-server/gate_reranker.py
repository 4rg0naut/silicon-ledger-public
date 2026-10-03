#!/usr/bin/env python3
"""Gate the Qwen3-Reranker bundle against its published reference.json.

The zoo ships reference.json with six (query, doc) pairs -- three relevant, three not, one of them
Japanese -- plus the official P(yes) for each and the expected ranking within each pair group. This
reproduces the host recipe exactly (prefix + body + suffix, add_special_tokens=False, right-pad to
the grid, truncate only the body) and checks:

  1. every relevant pair scores far above every irrelevant pair,
  2. each relevant doc outranks the irrelevant doc sharing its query,
  3. the numbers match the published engine gate (|delta| < 5e-4).

A reranker that silently scores wrong would still "improve" retrieval sometimes, so this is checked
before it is used for anything.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
BUNDLE_DIR = ROOT / "models" / "qwen3-reranker"
REF = BUNDLE_DIR / "reference.json"
AIMODEL = BUNDLE_DIR / "qwen3-reranker-0.6b_float16_s512_static.aimodel"


def main() -> int:
    ref = json.loads(REF.read_text())
    seq_len = ref["seq_len"]
    pad = ref["pad_token_id"]
    prefix, suffix = ref["prefix"], ref["suffix"]
    instruction = ref["default_instruction"]

    from tokenizers import Tokenizer
    from coreai.runtime import AIModel, NDArray, ComputeUnitKind, SpecializationOptions

    tok = Tokenizer.from_file(str(BUNDLE_DIR / "tokenizer" / "tokenizer.json"))
    pre = tok.encode(prefix, add_special_tokens=False).ids
    suf = tok.encode(suffix, add_special_tokens=False).ids
    budget = seq_len - len(pre) - len(suf)
    print(f"grid S={seq_len}  prefix={len(pre)} tok  suffix={len(suf)} tok  body budget={budget}")

    # the Core AI runtime is async; run it on a dedicated loop, as the embed server does
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()

    def run(coro):
        return asyncio.run_coroutine_threadsafe(coro, loop).result()

    # GPU, not ANE. The ANE delegate returns a CONSTANT [0.5, 0.5] for every pair -- no error, no
    # warning, a plausible-looking "uncertain" score. Measured on this machine:
    #     ANE [0.5, 0.5]  vs  GPU [0.00619, 0.9937]  vs  CPU [0.006306, 0.994]  (official 0.993775)
    # The zoo's own gate and latency numbers are GPU-delegate ("M4 Max GPU"), so the ANE path was
    # never validated for this bundle. Use what was verified.
    opts = SpecializationOptions.from_preferred_compute_unit_kind(ComputeUnitKind.gpu())
    t0 = time.time()
    model = run(AIModel.load(AIMODEL, specialization_options=opts))
    fn = model.load_function("main")
    print(f"loaded in {time.time() - t0:.2f}s")

    def score(query: str, doc: str) -> float:
        body = f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}"
        b = tok.encode(body, add_special_tokens=False).ids[:budget]
        ids = pre + b + suf
        real = len(ids)
        padded = ids + [pad] * (seq_len - real)
        mask = [1] * real + [0] * (seq_len - real)
        out = run(fn({
            "input_ids": NDArray(np.asarray([padded], dtype=np.int32)),
            "attention_mask": NDArray(np.asarray([mask], dtype=np.int32)),
        }))
        probs = out["probs"].numpy().reshape(-1)
        p = float(probs[1])
        del out
        return p

    expected = ref["scores"]
    official = ref["official_scores"]
    print(f"\n{'pair':<14}{'P(yes)':>12}{'official':>12}{'|d|':>10}  relevant")
    worst = 0.0
    got = {}
    for name, pair in ref["pairs"].items():
        p = score(pair["query"], pair["doc"])
        got[name] = p
        d = abs(p - expected[name])
        worst = max(worst, d)
        print(f"{name:<14}{p:>12.6f}{expected[name]:>12.6f}{d:>10.2e}  {pair['relevant']}")

    print()
    ok = True
    if worst >= 5e-4:
        print(f"  FAIL: worst |delta| {worst:.2e} >= 5e-4 vs the published engine gate")
        ok = False
    else:
        print(f"  PASS: worst |delta| {worst:.2e} < 5e-4 vs the published engine gate")

    for group, members in ref["rank_groups"].items():
        ranked = sorted(members, key=lambda m: -got[m])
        good = ranked == members
        print(f"  {'PASS' if good else 'FAIL'}: {group}: {ranked}")
        ok &= good

    rel = [v for k, v in got.items() if ref["pairs"][k]["relevant"]]
    irr = [v for k, v in got.items() if not ref["pairs"][k]["relevant"]]
    sep = min(rel) - max(irr)
    print(f"  {'PASS' if sep > 0 else 'FAIL'}: separation min(relevant) - max(irrelevant) = {sep:+.6f}")
    ok &= sep > 0

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
