#!/usr/bin/env python3
"""Run Von's own authored144 comparison suite against HF and against our ANE build.

This reproduces `benchmarks/run_comparison.py`'s scoring exactly (raw accuracy, balanced accuracy,
mean latency) but swaps the model call, so the two rows are directly comparable:

    HF (ModernBERT-Large, fp32, CPU)   -- the reference
    OURS (ANE, fp16, 3 regions)        -- the port

The scoring logic is copied from `src/von/backends/berta_backend.py::evaluate_choice`, not invented:
for each option build the hypothesis `"{instructions} {description}"`, run the NLI pair
(premise=state, hypothesis), take the ENTAILMENT logit, and argmax over options.

The published ladder this lands next to (Von's own run_comparison.py):
    Von (ModernBERT-Large)  790 MB   ~1.2 GB RAM (CPU)
    Laya 421M (RLCD)        840 MB   ~1.1 GB RAM (CPU)
    OpenJev (Qwen3.5-4B)    3.01 GB  RTX 3090   81.3% balanced acc  ~48 ms

usage:
    python bench/von_authored144.py --variant v1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import threading
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "models" / "von-1.0"
DATA = ROOT / "work" / "von-repo" / "benchmarks" / "data" / "authored144.jsonl"
SEQ_LEN = 256
MAX_LEN = 512


def load_rows(path: Path, limit: int = 0):
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    return rows[:limit] if limit else rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="v1", help="which exported variant to load")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    cfg = json.loads((MODEL_DIR / "config.json").read_text())
    pad_id = cfg["pad_token_id"]
    # entailment index, read from the config rather than assumed
    entail_idx = next(int(k) for k, v in cfg["id2label"].items() if "entail" in v.lower())

    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    hf = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR, dtype=torch.float32).eval()

    aot = (ROOT / f"work/exports/von-{args.variant}/aot_h16g_ane"
           / f"von-1.0_{args.variant}_float16_s256_ane.h16g.aimodelc")
    from coreai.runtime import AIModel, NDArray, ComputeUnitKind, SpecializationOptions
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    run = lambda c: asyncio.run_coroutine_threadsafe(c, loop).result()
    opts = SpecializationOptions.from_preferred_compute_unit_kind(ComputeUnitKind.neural_engine())
    ane = run(AIModel.load(aot, specialization_options=opts))
    fn = ane.load_function("main")

    rows = load_rows(DATA, args.limit)
    print(f"  authored144: {len(rows)} rows | entail_idx={entail_idx} | ANE bundle {aot.name}")

    def score_hf(premise: str, hyp: str) -> float:
        enc = tok(premise, hyp, truncation=True, max_length=MAX_LEN, return_tensors="pt")
        with torch.no_grad():
            return float(hf(**enc).logits[0, entail_idx])

    def score_ane(premise: str, hyp: str) -> float:
        enc = tok(premise, hyp, truncation=True, max_length=MAX_LEN, return_tensors="pt")
        ids, am = enc["input_ids"], enc["attention_mask"]
        real = ids.shape[1]
        ids = F.pad(ids, (0, SEQ_LEN - real), value=pad_id)
        am = F.pad(am, (0, SEQ_LEN - real), value=0)
        out = run(fn({"input_ids": NDArray(ids.numpy().astype(np.int32)),
                      "attention_mask": NDArray(am.numpy().astype(np.int32))}))
        v = float(np.asarray(out["logits"].numpy()).reshape(-1)[entail_idx])
        del out
        return v

    results = {}
    for name, score in (("HF (fp32, CPU)", score_hf), ("OURS (ANE, fp16)", score_ane)):
        correct = 0
        lat = []
        cls_c, cls_t = defaultdict(int), defaultdict(int)
        agree = 0
        for r in rows:
            expected = r["options"][r["label"]]["id"]
            t0 = time.perf_counter()
            scores = [score(r["state"], f"{r['question']} {o['description']}") for o in r["options"]]
            lat.append((time.perf_counter() - t0) * 1000.0)
            pred = r["options"][int(np.argmax(scores))]["id"]
            if pred == expected:
                correct += 1
                cls_c[expected] += 1
            cls_t[expected] += 1
            results.setdefault(name, {}).setdefault("preds", []).append(pred)
        recalls = [cls_c[c] / cls_t[c] for c in cls_t if cls_t[c]]
        raw = correct / len(rows)
        bal = sum(recalls) / len(recalls) if recalls else 0.0
        results[name] = {"raw": raw, "balanced": bal, "median_ms": statistics.median(lat),
                         "mean_ms": statistics.mean(lat), "preds": results[name]["preds"]}
        print(f"\n  {name}")
        print(f"    raw accuracy      {raw*100:.1f}%")
        print(f"    balanced accuracy {bal*100:.1f}%")
        print(f"    latency           median {statistics.median(lat):.0f} ms  mean {statistics.mean(lat):.0f} ms"
              f"  ({len(rows)} rows x {len(rows[0]['options'])} options)")

    a, b = results["HF (fp32, CPU)"], results["OURS (ANE, fp16)"]
    agree = sum(1 for x, y in zip(a["preds"], b["preds"]) if x == y)
    print(f"\n  === port fidelity ===")
    print(f"    HF vs ANE prediction agreement: {agree}/{len(rows)} = {agree/len(rows)*100:.1f}%")
    print(f"    balanced accuracy delta: {(b['balanced']-a['balanced'])*100:+.2f} points")
    print(f"\n  === the published ladder this sits next to ===")
    print(f"    Von (ModernBERT-Large) 790 MB CPU   -- Von's own run")
    print(f"    Laya 421M (RLCD)       840 MB CPU")
    print(f"    OpenJev (Qwen3.5-4B)  3.01 GB GPU   81.3% balanced  ~48 ms")

    if args.out:
        args.out.write_text(json.dumps(
            {k: {kk: vv for kk, vv in v.items() if kk != "preds"} for k, v in results.items()}
            | {"agreement": agree / len(rows), "rows": len(rows)}, indent=2))
        print(f"\n  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
