#!/usr/bin/env python3
"""Benchmark a Core ML encoder across compute units.

Measures per-call latency for CPU_ONLY / CPU_AND_GPU / ALL on identical inputs,
so the only variable is where Core ML places the work.
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import coremltools as ct
from transformers import AutoTokenizer

MODEL = "sentence-transformers/all-MiniLM-L6-v2"

TEXTS = [
    "The neural engine accelerates dense matrix multiplication.",
    "Where are form fields validated before a form is saved?",
    "Graph traversal with personalized pagerank improves multi hop retrieval.",
    "A semantic graph stores relations between concepts rather than plain text.",
    "Static embedding models trade accuracy for a very small footprint.",
    "The quick brown fox jumps over the lazy dog.",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mlpackage", default="models/minilm128.mlpackage")
    ap.add_argument("--seq", type=int, default=128)
    ap.add_argument("--iters", type=int, default=60)
    ap.add_argument("--only", default=None, help="run only this compute unit (for A/B tracing)")
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(MODEL)
    encs = [
        tok(t, return_tensors="np", padding="max_length", truncation=True, max_length=args.seq)
        for t in TEXTS
    ]
    inputs = [
        {
            "input_ids": e["input_ids"].astype(np.int32),
            "attention_mask": e["attention_mask"].astype(np.int32),
        }
        for e in encs
    ]

    units = [
        ("CPU_ONLY", ct.ComputeUnit.CPU_ONLY),
        ("CPU_AND_GPU", ct.ComputeUnit.CPU_AND_GPU),
        ("ALL", ct.ComputeUnit.ALL),
    ]
    if args.only:
        units = [u for u in units if u[0] == args.only]

    results = {}
    print(f"{'compute_units':<14}{'mean':>10}{'median':>10}{'p95':>10}{'min':>10}{'emb/s':>10}")
    for name, cu in units:
        try:
            model = ct.models.MLModel(args.mlpackage, compute_units=cu)
        except Exception as exc:  # noqa: BLE001
            print(f"{name:<14} LOAD FAILED: {type(exc).__name__}: {str(exc)[:60]}")
            continue

        for i in range(4):  # warmup
            model.predict(inputs[i % len(inputs)])

        samples = []
        for i in range(args.iters):
            payload = inputs[i % len(inputs)]
            t0 = time.perf_counter()
            out = model.predict(payload)
            samples.append(time.perf_counter() - t0)

        arr = np.asarray(samples)
        results[name] = (arr, out["embedding"][0])
        print(
            f"{name:<14}{arr.mean()*1e3:>9.2f}ms{np.median(arr)*1e3:>9.2f}ms"
            f"{np.percentile(arr, 95)*1e3:>9.2f}ms{arr.min()*1e3:>9.2f}ms"
            f"{1.0/arr.mean():>10.0f}"
        )

    # correctness across placements: same vector regardless of device
    if len(results) >= 2:
        names = list(results)
        base = results[names[0]][1]
        print("\n--- cross-placement agreement (cosine vs %s) ---" % names[0])
        for n in names[1:]:
            v = results[n][1]
            cos = float(np.dot(base, v) / (np.linalg.norm(base) * np.linalg.norm(v)))
            print(f"  {n:<14} cosine = {cos:.6f}")

    if "CPU_ONLY" in results and "ALL" in results:
        speed = results["CPU_ONLY"][0].mean() / results["ALL"][0].mean()
        print(f"\nspeedup ALL vs CPU_ONLY: {speed:.2f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
