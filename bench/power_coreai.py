#!/usr/bin/env python3
"""Which accelerator actually ran a Core AI graph? — power-rail A/B.

xctrace's `ane-hw-intervals` reports NOTHING for Core AI graphs (verified: a Core ML
control run in the same session showed 269 intervals), so ANE attribution has to come
from the power rails instead. This runs the granite-runner binary once per compute-unit
preference while sampling `ane_power,gpu_power,cpu_power`.

    cd "$(git rev-parse --show-toplevel)"
    sudo HF_HOME=$PWD/models/hf .venv/bin/python bench/power_coreai.py --iters 3000

Interpretation:
  * ANE rail high on `neuralEngine` and idle on `cpuOnly`  -> the ANE really ran it
  * GPU rail high on `neuralEngine`                        -> the preference fell back to GPU
  * neither rail moves                                     -> CPU fallback
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

import numpy as np

from _power import POWER_RE, parse_power  # single source: bench/_power.py

BIN = "tools/granite-runner/.build/release/granite-runner"
BUNDLE_DIR = "models/granite97m/macos/fp32-s128"
# --bundle overrides the model path so the same power A/B can be run on any variant.
BUNDLE_OVERRIDE = None
TOKENIZER_DIR = "/Volumes/M4-Partage/local_ai_stack/work/granite-embedding-97m/source"
REFERENCE = "/Volumes/M4-Partage/local_ai_stack/work/granite-embedding-97m/fixtures/golden_s128.json"
# Default locations on the Studio; override with --tokenizer / --reference off-box.
CASES = ["neuralEngine", "gpu", "cpuOnly"]


def run_case(compute: str, iters: int, interval_ms: int,
             tokenizer_dir: str, reference: str, outdir: str) -> dict:
    args = [
        BIN,
        BUNDLE_OVERRIDE or f"{BUNDLE_DIR}/granite97m_fp32_s128_bound.aimodel",
        tokenizer_dir,
        reference,
        "--compute", compute,
        "--iters", str(iters),
    ]
    log_path = f"{outdir}/power_{compute}.txt"
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    pm = subprocess.Popen(
        ["powermetrics", "--samplers", "ane_power,gpu_power,cpu_power", "-i", str(interval_ms)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    time.sleep(2.0)  # let the sampler settle before the load starts

    t0 = time.perf_counter()
    proc = subprocess.run(args, capture_output=True, text=True)
    elapsed = time.perf_counter() - t0

    pm.terminate()
    try:
        raw = pm.communicate(timeout=15)[0]
    except subprocess.TimeoutExpired:
        pm.kill()
        raw = pm.communicate()[0]
    with open(log_path, "w") as fh:
        fh.write(raw or "")

    median_ms = None
    for line in proc.stdout.splitlines():
        if line.startswith("warm median"):
            try:
                median_ms = float(line.split(":")[1].split("ms")[0].strip())
            except (IndexError, ValueError):
                pass
    gate = "PASS" if "gate=PASS" in proc.stdout else "FAIL/unknown"

    rails = parse_power(raw or "")
    out = {"compute": compute, "elapsed": elapsed, "median_ms": median_ms,
           "gate": gate, "log": log_path, "rails": {}}
    for rail in ("ANE", "GPU", "CPU"):
        vals = rails.get(rail, [])
        out["rails"][rail] = float(np.mean(vals)) if vals else float("nan")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=500)
    ap.add_argument("--bundle", help="override the model path (.aimodel or .aimodelc)")
    ap.add_argument("--iters", type=int, default=3000)
    ap.add_argument("--tokenizer", default=TOKENIZER_DIR,
                    help="tokenizer dir for granite-runner (default: Studio path)")
    ap.add_argument("--reference", default=REFERENCE,
                    help="golden reference JSON for the correctness gate")
    ap.add_argument("--outdir", default=None,
                    help="capture dir for power_<compute>.txt (default: fresh "
                         "bench/energy-<UTCstamp>/; never an EXP-NN dir belonging "
                         "to another machine's experiment)")
    args = ap.parse_args()
    if args.outdir is None:
        args.outdir = f"bench/energy-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    os.makedirs(args.outdir, exist_ok=True)

    try:
        import json as _json
        from identity import identity
        print(f"  identity: {_json.dumps(identity(), separators=(',', ':'))}")
    except Exception as e:
        print(f"  identity: unavailable ({e})", file=sys.stderr)

    global BUNDLE_OVERRIDE
    BUNDLE_OVERRIDE = args.bundle
    if os.geteuid() != 0:
        print("ERROR: powermetrics needs root. Re-run with sudo.", file=sys.stderr)
        return 2

    results = []
    print(f"{'compute':<14}{'gate':<8}{'median':>10}{'ANE mW':>10}{'GPU mW':>10}{'CPU mW':>10}")
    for compute in CASES:
        r = run_case(compute, args.iters, args.interval, args.tokenizer, args.reference, args.outdir)
        results.append(r)
        med = f"{r['median_ms']:.2f}ms" if r["median_ms"] is not None else "?"
        print(f"{compute:<14}{r['gate']:<8}{med:>10}"
              f"{r['rails']['ANE']:>10.1f}{r['rails']['GPU']:>10.1f}{r['rails']['CPU']:>10.1f}")

    print("\n--- raw logs ---")
    for r in results:
        print(f"  {r['compute']:<14} {r['log']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
