#!/usr/bin/env python3
"""A/B power measurement for the Core ML encoder (ALL vs CPU_ONLY).

Runs the SAME workload twice while sampling Apple's power rails, so the only
variable is where Core ML places the work.

    cd "$(git rev-parse --show-toplevel)"
    sudo .venv-conv/bin/python bench/power_ab.py --seconds 15

Writes:
    bench/power_ALL.txt        raw powermetrics output, ALL placement
    bench/power_CPU_ONLY.txt   raw powermetrics output, CPU-only placement

The raw files are the deliverable — the inline summary is best-effort because
powermetrics' exact wording varies between macOS releases.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time

import numpy as np
import coremltools as ct
from transformers import AutoTokenizer

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TEXTS = [
    "The neural engine accelerates dense matrix multiplication.",
    "Where are form fields validated before a form is saved?",
    "Graph traversal with personalized pagerank improves multi hop retrieval.",
    "A semantic cache stores relations between concepts rather than plain text.",
]

POWER_RE = re.compile(r"(ANE|GPU|CPU|Combined)\s+Power[^:]*:\s*([\d.]+)\s*(mW|W)")


def parse_power(text: str) -> dict[str, list[float]]:
    """Collect power samples in milliwatts, keyed by rail."""
    out: dict[str, list[float]] = {}
    for rail, value, unit in POWER_RE.findall(text):
        mw = float(value) * (1000.0 if unit == "W" else 1.0)
        out.setdefault(rail, []).append(mw)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mlpackage", default="models/minilm128.mlpackage")
    ap.add_argument("--seq", type=int, default=128)
    ap.add_argument("--seconds", type=float, default=15.0, help="sampling window per case")
    ap.add_argument("--interval", type=int, default=500, help="powermetrics interval (ms)")
    args = ap.parse_args()

    try:
        import json as _json
        from identity import identity
        print(f"  identity: {_json.dumps(identity(), separators=(',', ':'))}")
    except Exception as e:
        print(f"  identity: unavailable ({e})", file=sys.stderr)

    if os.geteuid() != 0:
        print("ERROR: powermetrics needs root. Re-run with sudo.", file=sys.stderr)
        return 2

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

    cases = [("ALL", ct.ComputeUnit.ALL), ("CPU_ONLY", ct.ComputeUnit.CPU_ONLY)]
    summary = []

    for name, cu in cases:
        model = ct.models.MLModel(args.mlpackage, compute_units=cu)
        for i in range(10):  # warmup, incl. ANE program load
            model.predict(inputs[i % len(inputs)])

        log_path = f"bench/power_{name}.txt"
        pm = subprocess.Popen(
            ["powermetrics", "--samplers", "ane_power,gpu_power,cpu_power", "-i", str(args.interval)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        time.sleep(2.0)  # let the sampler settle

        t0 = time.perf_counter()
        n = 0
        while time.perf_counter() - t0 < args.seconds:
            model.predict(inputs[n % len(inputs)])
            n += 1
        elapsed = time.perf_counter() - t0

        pm.terminate()
        try:
            raw = pm.communicate(timeout=15)[0]
        except subprocess.TimeoutExpired:
            pm.kill()
            raw = pm.communicate()[0]
        with open(log_path, "w") as fh:
            fh.write(raw or "")

        rate = n / elapsed
        rails = parse_power(raw or "")
        print(f"\n=== {name} ===")
        print(f"  inferences      : {n} in {elapsed:.1f}s  ->  {rate:.0f} emb/s")
        print(f"  raw log         : {log_path} ({len(raw or '')} bytes)")
        if not rails:
            print("  power           : NOT PARSED (send me the raw log)")
        for rail in ("ANE", "GPU", "CPU", "Combined"):
            if rail in rails:
                arr = np.asarray(rails[rail])
                mean_mw = arr.mean()
                mj_per_emb = (mean_mw / 1000.0) / rate * 1000.0
                print(
                    f"  {rail + ' power':<16}: mean {mean_mw:8.1f} mW  "
                    f"max {arr.max():8.1f} mW  -> {mj_per_emb:7.3f} mJ/embedding"
                )
        summary.append((name, rate, rails))

    print("\n=== comparison ===")
    if len(summary) == 2:
        (n1, r1, p1), (n2, r2, p2) = summary
        print(f"  throughput  : {n1} {r1:.0f} emb/s  vs  {n2} {r2:.0f} emb/s")
        if "ANE" in p1 or "ANE" in p2:
            a1 = np.mean(p1.get("ANE", [0.0]))
            a2 = np.mean(p2.get("ANE", [0.0]))
            print(f"  ANE power   : {n1} {a1:.1f} mW  vs  {n2} {a2:.1f} mW")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
