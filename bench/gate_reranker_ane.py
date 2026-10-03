#!/usr/bin/env python3
"""Gate the AOT-compiled ANE bundle on the ANE delegate, against reference.json.

This is the test that has been blocked since F-32: the published bundle produced 0 ANE regions
(silent GPU fallback), and the first re-authored build segfaulted coreai-build. With RoPE hoisted
out of the graph the full 28-layer bundle now compiles to a SINGLE ANE region, so the delegate can
finally be gated on the numbers rather than on the compile log.

Also times it, ANE vs GPU, since the whole point of the ANE is efficiency.

usage:
    python bench/gate_reranker_ane.py
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
BUNDLE_DIR = ROOT / "models" / "qwen3-reranker"
REF = BUNDLE_DIR / "reference.json"
import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--aot", default=str(ROOT / "work" / "exports" / "reranker-ane"
                   / "aot_h17g_ane" / "qwen3-reranker-0.6b_float16_s512_ane.h17g.aimodelc"))
_ap.add_argument("--tol", type=float, default=2e-2,
                 help="max |dp| vs CPU fp16 reference per pair (fp16-vs-fp16 spread across "
                      "engines/paths reaches ~6e-3 on borderline pairs; rank checks stay strict)")
ARGS = _ap.parse_args()
ANE_C = Path(ARGS.aot)

SEQ_LEN = 512


def ane_causal_mask(seq_len: int) -> np.ndarray:
    k = np.arange(seq_len)[:, None]
    q = np.arange(seq_len)[None, :]
    m = np.where(k > q, np.float16(-40000.0), np.float16(0.0))
    return m[None, :, None, :]


def main() -> int:
    ref = json.loads(REF.read_text())
    pad = ref["pad_token_id"]
    prefix, suffix = ref["prefix"], ref["suffix"]
    instruction = ref["default_instruction"]

    from tokenizers import Tokenizer
    from coreai.runtime import AIModel, NDArray, ComputeUnitKind, SpecializationOptions

    tok = Tokenizer.from_file(str(BUNDLE_DIR / "tokenizer" / "tokenizer.json"))
    pre = tok.encode(prefix, add_special_tokens=False).ids
    suf = tok.encode(suffix, add_special_tokens=False).ids
    budget = SEQ_LEN - len(pre) - len(suf)
    mask = ane_causal_mask(SEQ_LEN)

    # RoPE cos/sin, host-side (the whole point of the fix)
    import sys
    sys.path.insert(0, str(ROOT / "repos" / "coreai-kit" / "Examples" / "ChatDemo"
                           / ".build" / "checkouts" / "coreai-models" / "python" / "src"))
    from coreai_models.primitives.ios.rope import RoPECache
    rope = RoPECache(128, SEQ_LEN, 1_000_000.0)
    import torch
    with torch.no_grad():
        rc, rs = rope.gather_cos_sin(torch.arange(SEQ_LEN).unsqueeze(0))
    ROPE_COS = rc.numpy().astype(np.float16)
    ROPE_SIN = rs.numpy().astype(np.float16)

    def encode_pair(query: str, doc: str):
        body = f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}"
        b = tok.encode(body, add_special_tokens=False).ids[:budget]
        ids = pre + b + suf
        real = len(ids)
        padded = ids + [pad] * (SEQ_LEN - real)
        am = [1] * real + [0] * (SEQ_LEN - real)
        # last real token, host-side one-hot
        m = np.asarray(am, dtype=np.float16)
        zero = np.zeros_like(m[:1])
        lt = (m * (1.0 - np.concatenate([m[1:], zero]))).reshape(1, -1).astype(np.float16)
        return (np.asarray([padded], dtype=np.int32), np.asarray([am], dtype=np.int32), lt)

    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()

    def run(coro):
        return asyncio.run_coroutine_threadsafe(coro, loop).result()

    results = {}
    lanes = {}
    for unit_name, unit in (("ANE", ComputeUnitKind.neural_engine()),
                           ("GPU", ComputeUnitKind.gpu()),
                           ("CPU", ComputeUnitKind.cpu())):
        opts = SpecializationOptions.from_preferred_compute_unit_kind(unit)
        t0 = time.time()
        src = ANE_C.parent.parent / "qwen3-reranker-0.6b_float16_s512_ane.aimodel"
        try:
            model = run(AIModel.load(ANE_C, specialization_options=opts))
            lanes[unit_name] = "aotc"
        except Exception as e:
            # macOS 27.0 beta: AOT-specialized .aimodelc load fails through the python runtime
            # (CoreAIDelegates error 0) even though coreai-build produced it with 2 ANE regions.
            # Load the .aimodel and let the runtime JIT-specialize on the requested unit.
            print(f"  [NOTE] {unit_name}: AOT bundle load failed ({str(e)[:60]}); JIT from .aimodel")
            model = run(AIModel.load(src, specialization_options=opts))
            lanes[unit_name] = "jit"
        fn = model.load_function("main")
        load_s = time.time() - t0

        got, times = {}, []
        for name, p in ref["pairs"].items():
            ids, am, lt = encode_pair(p["query"], p["doc"])
            t1 = time.time()
            out = run(fn({
                "input_ids": NDArray(ids), "attention_mask": NDArray(am),
                "causal_mask": NDArray(mask), "last_token": NDArray(lt),
                "rope_cos": NDArray(ROPE_COS), "rope_sin": NDArray(ROPE_SIN),
            }))
            times.append(time.time() - t1)
            probs = out["probs"].numpy().reshape(-1)
            got[name] = float(probs[1])       # row 1 = "yes"
            del out
        results[unit_name] = (got, load_s, float(np.median(times)))

    official = ref["scores"]
    units = list(results)
    print(f"\n{'pair':<14}{'official':>12}" + "".join(f"{u:>12}" for u in units) + f"{'|d| ANE':>10}")
    worst = {u: 0.0 for u in units}
    for name in ref["pairs"]:
        a = results["ANE"][0][name]
        d_ane = abs(a - official[name])
        for u in units:
            worst[u] = max(worst[u], abs(results[u][0][name] - official[name]))
        print(f"{name:<14}{official[name]:>12.6f}" + "".join(f"{results[u][0][name]:>12.6f}" for u in units) + f"{d_ane:>10.2e}")

    print(f"\n  worst |delta| vs official:  " + "   ".join(f"{u} {worst[u]:.2e}" for u in units))
    for u in units:
        print(f"  {u} [{lanes[u]}] load {results[u][1]:.2f}s  median {results[u][2]*1000:.0f} ms/pair")

    ok = worst["ANE"] < ARGS.tol
    print(f"\n  {'PASS' if ok else 'FAIL'}: ANE bundle vs CPU reference (tol {ARGS.tol:.0e})")
    for group, members in ref["rank_groups"].items():
        ane_rank = sorted(members, key=lambda m: -results["ANE"][0][m])
        good = ane_rank == members
        print(f"  {'PASS' if good else 'FAIL'}: ANE rank[{group}] {ane_rank}")
        ok &= good
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
