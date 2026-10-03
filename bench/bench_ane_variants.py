#!/usr/bin/env python3
"""Benchmark the ANE residency sweep variants: latency, load, and where the work ran.

Region count alone is ambiguous — 2 regions could mean "one big ANE plan" or "two tiny ones".
The zoo's own measurement is that FEWER regions is better (49 -> 25 halved their load time),
because each region boundary is an ANE<->GPU transfer. So the deciding numbers are:

  * ANE memory traffic + interrupts  (did the ANE do the work?)
  * GPU mean power                   (did the GPU do it instead?)
  * warm median + load               (what did it cost?)

Each variant is run under tools/enginemon (unprivileged IOReport) with the granite runner as
the child, so both the runtime counters and the runner's own gate/timings come from one pass.

usage: .venv/bin/python bench/bench_ane_variants.py
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SWEEP = ROOT / "work" / "exports" / "granite-embedding-97m" / "ane-sweep"
ENGINEMON = ROOT / "tools" / "enginemon" / "enginemon"
RUNNER = ROOT / "tools" / "granite-runner" / ".build" / "out" / "Products" / "Release" / "granite-runner"
TOK = ROOT / "models" / "granite97m" / "macos" / "fp32-s128" / "tokenizer"
REF = ROOT / "models" / "granite97m" / "macos" / "fp32-s128" / "reference.json"

ARMS = [
    ("fp32 (published, GPU)", ROOT / "models/granite97m/macos/fp32-s128/aot-ane/"
     "granite97m_fp32_s128_bound.h16g.aimodelc"),
    ("fp16 v0 as-is", SWEEP / "v0/aot/granite97m_fp16_s128_v0.h16g.aimodelc"),
    ("fp16 v1 +fp16 softmax", SWEEP / "v1/aot/granite97m_fp16_s128_v1.h16g.aimodelc"),
    ("fp16 v2 +f16 scale", SWEEP / "v2/aot/granite97m_fp16_s128_v2.h16g.aimodelc"),
    ("fp16 v3 +fp16 pooling", SWEEP / "v3/aot/granite97m_fp16_s128_v3.h16g.aimodelc"),
    ("w8+fp16 (int8 weights)", ROOT / "work/exports/granite-embedding-97m/w8fp16/s128/aot/"
     "granite97m_w8_fp16_s128.h16g.aimodelc"),
]

ANE_BYTES = re.compile(r"ANE activity\s+(\d+) B moved, (\d+) interrupts")
GPU_MW = re.compile(r"GPU Energy\s+([\d.]+) mW")
MEDIAN = re.compile(r"warm median\s+:\s+([\d.]+) ms")
LOAD = re.compile(r"^load\s+:\s+(\d+) ms", re.M)
GATE = re.compile(r"numeric gate : min cosine ([\d.]+) \| max \|err\| ([\d.e+-]+)")
FIRST = re.compile(r"first after load : ([\d.]+) ms")


def run_arm(label: str, bundle: Path, iters: int, seconds: int) -> dict:
    if not bundle.exists():
        return {"arm": label, "error": f"missing {bundle}"}
    cmd = [str(ENGINEMON), "--interval", "500", "--duration", str(seconds), "--",
           str(RUNNER), str(bundle), str(TOK), str(REF), "--compute", "neuralEngine",
           "--iters", str(iters)]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    out = p.stdout
    m, g, med, load, gate, first = (ANE_BYTES.search(out), GPU_MW.search(out),
                                    MEDIAN.search(out), LOAD.search(out),
                                    GATE.search(out), FIRST.search(out))
    r = {"arm": label, "bundle": str(bundle)}
    r["ane_bytes"] = int(m.group(1)) if m else None
    r["ane_interrupts"] = int(m.group(2)) if m else None
    r["gpu_mw"] = float(g.group(1)) if g else None
    r["warm_median_ms"] = float(med.group(1)) if med else None
    r["load_ms"] = int(load.group(1)) if load else None
    r["first_ms"] = float(first.group(1)) if first else None
    r["min_cosine"] = float(gate.group(1)) if gate else None
    r["max_abs_err"] = float(gate.group(2)) if gate else None
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=1500)
    ap.add_argument("--seconds", type=int, default=25)
    args = ap.parse_args()

    for tool in (ENGINEMON, RUNNER):
        if not tool.exists():
            print(f"missing {tool}", file=sys.stderr)
            return 2

    results = [run_arm(label, bundle, args.iters, args.seconds) for label, bundle in ARMS]

    print("\n" + "=" * 100)
    print("ANE RESIDENCY SWEEP — runtime benchmark (M4, macOS 27, AOT h16g, --compute neuralEngine)")
    print("=" * 100)
    hdr = (f"{'arm':<24}{'ANE moved':>13}{'ANE intr':>10}{'GPU mW':>9}"
           f"{'load':>8}{'first':>8}{'warm ms':>9}{'cos':>13}{'max err':>10}")
    print(hdr)
    print("-" * 100)
    for r in results:
        if r.get("error"):
            print(f"{r['arm']:<24}  {r['error']}")
            continue
        gb = (r["ane_bytes"] or 0) / 1e9
        print(f"{r['arm']:<24}{gb:>12.1f}G{r['ane_interrupts'] or 0:>10}"
              f"{r['gpu_mw'] or 0:>9.1f}{r['load_ms'] or 0:>8}{r['first_ms'] or 0:>8.1f}"
              f"{r['warm_median_ms'] or 0:>9.2f}{r['min_cosine'] or 0:>13.9f}"
              f"{r['max_abs_err'] or 0:>10.2e}")

    out = SWEEP / "bench.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print(f"\nrecord: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
