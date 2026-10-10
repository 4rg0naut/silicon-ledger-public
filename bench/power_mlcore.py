#!/usr/bin/env python3
"""Core ML MiniLM power A/B — coremltools-free (macOS 27: Core AI is the headline stack, the
python coremltools wheel is gone from this workspace; the Core ML runtime + system
MLModel.compileModel remain). Same measurement contract as power_ab.py: fixed texts, ALL vs
CPU_ONLY, powermetrics rails, mJ/embedding = mean rail mW / measured rate.

    cd "$(git rev-parse --show-toplevel)"
    sudo .venv-conv/bin/python bench/power_mlcore.py --seconds 20

Expects bench/mlpower-runner (swiftc -O bench/mlpower-runner.swift -o bench/mlpower-runner)
and a compiled model (default models/minilm128.mlmodelc; compile once with
MLModel.compileModel via bench/mlcompile.swift or Xcode). Tokenization is offline via the
HF cache (HF_HUB_OFFLINE=1).
"""
from __future__ import annotations

import argparse
import os
import re
import struct
import subprocess
import sys
import time

import numpy as np

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TEXTS = [
    "The neural engine accelerates dense matrix multiplication.",
    "Where are form fields validated before a form is saved?",
    "Graph traversal with personalized pagerank improves multi hop retrieval.",
    "A semantic cache stores relations between concepts rather than plain text.",
]
from _power import POWER_RE, parse_power  # single source: bench/_power.py

RATE_RE = re.compile(r"mode=(\S+) n=(\d+) elapsed=([\d.]+) rate=([\d.]+)")


def dump_tokens(path: str, seq: int) -> None:
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(MODEL)
    encs = [
        tok(t, padding="max_length", truncation=True, max_length=seq) for t in TEXTS
    ]
    with open(path, "wb") as fh:
        fh.write(struct.pack("<ii", len(encs), seq))
        for e in encs:
            fh.write(struct.pack(f"<{seq}i", *e["input_ids"]))
        for e in encs:
            fh.write(struct.pack(f"<{seq}i", *e["attention_mask"]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelc", default="models/minilm128.mlmodelc")
    ap.add_argument("--seq", type=int, default=128)
    ap.add_argument("--seconds", type=float, default=15.0)
    ap.add_argument("--interval", type=int, default=500)
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

    toks = "/tmp/minilm_tokens.bin"
    dump_tokens(toks, args.seq)

    summary = []
    for name, mode in (("ALL", "all"), ("CPU_ONLY", "cpuOnly")):
        warm = subprocess.run(
            ["bench/mlpower-runner", args.modelc, mode, "2", toks],
            capture_output=True, text=True, check=True,
        )
        _ = warm

        pm = subprocess.Popen(
            ["powermetrics", "--samplers", "ane_power,gpu_power,cpu_power", "-i", str(args.interval)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        time.sleep(2.0)
        proc = subprocess.run(
            ["bench/mlpower-runner", args.modelc, mode, str(args.seconds), toks],
            capture_output=True, text=True,
        )
        pm.terminate()
        try:
            raw = pm.communicate(timeout=15)[0]
        except subprocess.TimeoutExpired:
            pm.kill()
            raw = pm.communicate()[0]
        with open(f"bench/power_{name}.txt", "w") as fh:
            fh.write(raw or "")

        m = RATE_RE.search(proc.stdout or "")
        if not m:
            print(f"  {name}: runner failed: {(proc.stderr or '')[:200]}", file=sys.stderr)
            return 1
        n, elapsed, rate = int(m.group(2)), float(m.group(3)), float(m.group(4))
        rails = parse_power(raw or "")
        print(f"\n=== {name} ===")
        print(f"  inferences      : {n} in {elapsed:.1f}s  ->  {rate:.0f} emb/s")
        if not rails:
            print("  power           : NOT PARSED")
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
    (n1, r1, p1), (n2, r2, p2) = summary
    print(f"  throughput  : {n1} {r1:.0f} emb/s  vs  {n2} {r2:.0f} emb/s")
    a1 = np.mean(p1.get("ANE", [0.0]))
    a2 = np.mean(p2.get("ANE", [0.0]))
    print(f"  ANE power   : {n1} {a1:.1f} mW  vs  {n2} {a2:.1f} mW")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
