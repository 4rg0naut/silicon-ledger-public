#!/usr/bin/env python3
"""Run the Laya ANE build: fidelity against the torch module, latency, and ANE residency.

The comparison target is the published Core ML port (`aac6fef/laya-multilingual-coreml-ane`):
**4.98 ms P50 / 5.31 ms P95 on an M3 Max at a 96-token budget**, 32 option slots, 59/59 fixtures.
Two differences must be stated when quoting our numbers against theirs:

  * our budget is **256 tokens**, not 96 — so much of any gap is budget, not efficiency;
  * their latency is on an **M3 Max**, ours on a base **M4**.

usage: .venv/bin/python bench/laya_ane_bench.py [--variant v1] [--runs 30]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import threading
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))

from export_laya_ane import MODEL_DIR, K_SLOTS, LayaANE, build_case, _set_variant  # noqa: E402

CASES = [
    ("refund", "The customer asks for a refund of a duplicate payment.",
     "Does the customer request a refund?", ["refund", "not a refund"]),
    ("billing", "Our card was charged twice for the same invoice this month.",
     "Which department should handle this?", ["billing", "tech", "sales"]),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="v1")
    ap.add_argument("--seq-len", type=int, default=256)
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--compute", choices=["neural_engine", "gpu", "cpu"], default="neural_engine",
                    help="which engine to specialize the Core AI graph for")
    args = ap.parse_args()

    aot = (ROOT / "work" / "exports" / "laya-ane" / "aot_h16g_ane"
           / f"laya-multilingual_{args.variant}_float16_s{args.seq_len}_ane.h16g.aimodelc")
    if not aot.exists():
        raise SystemExit(f"missing AOT bundle: {aot}")

    cfg = json.loads((MODEL_DIR / "encoder" / "config.json").read_text())
    head_cfg = json.loads((MODEL_DIR / "rl_agent_config.json").read_text())
    from safetensors.torch import load_file
    from transformers import AutoTokenizer

    sd = load_file(str(MODEL_DIR / "model.safetensors"))
    tok = AutoTokenizer.from_pretrained(MODEL_DIR / "tokenizer")

    _set_variant(args.variant)
    module = LayaANE(cfg, head_cfg, args.seq_len)
    module.load_hf(sd)
    module.eval()

    # ---- the ANE delegate ----
    from coreai.runtime import AIModel, NDArray, ComputeUnitKind, SpecializationOptions
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    run = lambda c: asyncio.run_coroutine_threadsafe(c, loop).result()
    unit = {"neural_engine": ComputeUnitKind.neural_engine, "gpu": ComputeUnitKind.gpu,
            "cpu": ComputeUnitKind.cpu}[args.compute]
    opts = SpecializationOptions.from_preferred_compute_unit_kind(unit())
    t0 = time.perf_counter()
    ane = run(AIModel.load(aot, specialization_options=opts))
    load_s = time.perf_counter() - t0
    fn = ane.load_function("main")
    print(f"  bundle     : {aot.name}")
    print(f"  compute    : {args.compute}")
    print(f"  load       : {load_s * 1000:.1f} ms")

    # ---- fidelity: ANE logits vs the fp32 torch module ----
    print(f"\n{'case':<10}{'torch argmax':>14}{'ANE argmax':>12}{'max|dlogit|':>13}")
    worst, agreement = 0.0, 0
    for name, state, _ins, opt_list in CASES:
        iid, am, sel, qt = build_case(tok, cfg, state, opt_list, args.seq_len)
        with torch.no_grad():
            ref = module(iid, am, sel, qt)[: len(opt_list)]
        out = run(fn({"input_ids": NDArray(iid.numpy().astype(np.int32)),
                      "attention_mask": NDArray(am.numpy().astype(np.int32)),
                      "selection": NDArray(sel.numpy().astype(np.float16)),
                      "qtype": NDArray(qt.numpy().astype(np.int32))}))
        got = torch.tensor(np.asarray(out["logits"].numpy()).reshape(-1))[: len(opt_list)]
        del out
        d = float((ref - got).abs().max())
        worst = max(worst, d)
        agreement += int(ref.argmax() == got.argmax())
        print(f"{name:<10}{int(ref.argmax()):>14}{int(got.argmax()):>12}{d:>13.2e}")
    print(f"  worst |dlogit| = {worst:.2e}   argmax {agreement}/{len(CASES)}")

    # ---- fidelity sweep across the input space (option count x length x qtype) ----
    import random
    rng = random.Random(0)
    WORDS = ("refund charge invoice account policy request cancel update delete sync export "
             "billing tech sales legal urgent normal pending closed open review").split()
    def phrase(n): return " ".join(rng.choice(WORDS) for _ in range(n))
    n_sweep, sweep_worst, sweep_agree, sweep_cases = 60, 0.0, 0, 0
    sweep_flips = []
    for i in range(n_sweep):
        n_opts = rng.randint(1, 8)
        opts = [phrase(rng.randint(1, 3)) for _ in range(n_opts)]
        state = phrase(rng.randint(5, 60))
        qt = rng.choice([0, 1, 2])
        iid, am, sel, qq = build_case(tok, cfg, state, opts, args.seq_len, qtype=qt)
        with torch.no_grad():
            ref = module(iid, am, sel, qq)[:n_opts]
        out = run(fn({"input_ids": NDArray(iid.numpy().astype(np.int32)),
                      "attention_mask": NDArray(am.numpy().astype(np.int32)),
                      "selection": NDArray(sel.numpy().astype(np.float16)),
                      "qtype": NDArray(qq.numpy().astype(np.int32))}))
        got = torch.tensor(np.asarray(out["logits"].numpy()).reshape(-1))[:n_opts]
        del out
        sweep_worst = max(sweep_worst, float((ref - got).abs().max()))
        if ref.argmax() != got.argmax():
            top2 = torch.topk(ref, min(2, n_opts)).values
            margin = float(top2[0] - top2[1]) if len(top2) > 1 else float("inf")
            sweep_flips.append((n_opts, qt, margin, float((ref - got).abs().max())))
        else:
            sweep_agree += 1
        sweep_cases += 1
    print(f"\n  fidelity sweep: {sweep_cases} random cases (1-8 options, qtype 0-2, "
          f"states 5-60 words)")
    print(f"    argmax agreement : {sweep_agree}/{sweep_cases}")
    print(f"    worst |dlogit|   : {sweep_worst:.2e}")
    for n_opts, qt, margin, d in sweep_flips:
        print(f"      FLIP: {n_opts} opts, qtype={qt}, torch top1-top2 margin={margin:.4f}, "
              f"max|dlogit|={d:.2e} -> {'near-tie' if margin < 0.1 else 'REAL DIVERGENCE'}")

    # ---- latency ----
    iid, am, sel, qt = build_case(tok, cfg, CASES[1][1], CASES[1][3], args.seq_len)
    ins = {"input_ids": NDArray(iid.numpy().astype(np.int32)),
           "attention_mask": NDArray(am.numpy().astype(np.int32)),
           "selection": NDArray(sel.numpy().astype(np.float16)),
           "qtype": NDArray(qt.numpy().astype(np.int32))}
    for _ in range(5):                       # warm
        out = run(fn(ins))
        del out
    lat = []
    for _ in range(args.runs):
        t = time.perf_counter()
        out = run(fn(ins)); del out
        lat.append((time.perf_counter() - t) * 1000.0)
    lat.sort()
    p50 = statistics.median(lat)
    p95 = lat[min(len(lat) - 1, int(0.95 * len(lat)))]
    print(f"\n  latency over {args.runs} calls (S={args.seq_len}, base M4, ANE):")
    print(f"    P50 = {p50:.2f} ms   P95 = {p95:.2f} ms   min = {lat[0]:.2f} ms")
    print(f"    the Core ML port's published number: 4.98 ms P50 / 5.31 ms P95 "
          f"(M3 Max, S=96)")
    print(f"    ratio vs their P50: {p50 / 4.98:.2f}x  (different budget AND different chip)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
