#!/usr/bin/env python3
"""System-wide ANE capture: does a Core AI graph use the Neural Engine?

WHY NOT PROCESS-SCOPED
----------------------
The earlier run attached xctrace to the launched process. If Core AI dispatches ANE work
to an out-of-process service, a process-scoped trace sees nothing even when the ANE IS
working -- so "0 intervals" would be a measurement artifact, not evidence.

This records SYSTEM-WIDE (`xctrace --all-processes`), so ANE activity is captured no
matter which process drives it.

CONTROLS (both required -- without them the result is uninterpretable)
  minilm-ALL        Core ML, compute_units=ALL  -> MUST show ANE intervals  (positive)
  minilm-CPU_AND_GPU Core ML, provably no ANE   -> MUST show ~none          (negative)
  granite-cpuOnly   Core AI, CPU only           -> MUST show ~none          (negative)
  granite-neuralEngine  Core AI, .neuralEngine  -> THE QUESTION

usage: .venv/bin/python bench/syswide_ane.py [--seconds 30] [--keep]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

BIN = os.path.join(ROOT, "tools/granite-runner/.build/out/Products/Release/granite-runner")
BASE = os.path.join(ROOT, "models/granite97m/macos/fp32-s128")
BUNDLE = f"{BASE}/granite97m_fp32_s128_bound.aimodel"
TOKENIZER = f"{BASE}/tokenizer"
REFERENCE = f"{BASE}/reference.json"

TEMPLATE = "Core AI"
STARTUP_GRACE = 6.0  # seconds to let the recording actually begin


def granite(compute: str, iters: int) -> list[str]:
    return [BIN, BUNDLE, TOKENIZER, REFERENCE, "--compute", compute, "--iters", str(iters)]


def minilm(unit: str, iters: int) -> list[str]:
    return [sys.executable, os.path.join(HERE, "bench_encoder.py"), "--only", unit, "--iters", str(iters)]


ARMS: list[tuple[str, str, object, str]] = [
    # label, kind, workload, expectation
    ("minilm-ALL", "positive", lambda: minilm("ALL", 5000), "ANE intervals EXPECTED"),
    ("minilm-CPU_AND_GPU", "negative", lambda: minilm("CPU_AND_GPU", 5000), "~none expected"),
    ("granite-cpuOnly", "negative", lambda: granite("cpuOnly", 1500), "~none expected"),
    ("granite-neuralEngine", "question", lambda: granite("neuralEngine", 2500), "THE QUESTION"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=30, help="xctrace --time-limit per arm")
    ap.add_argument("--keep", action="store_true", help="keep .trace bundles")
    args = ap.parse_args()

    try:
        from identity import identity
        print(f"  identity: {json.dumps(identity(), separators=(',', ':'))}")
    except Exception as e:
        print(f"  identity: unavailable ({e})", file=sys.stderr)

    if not os.path.exists(BIN):
        print(f"missing runner: {BIN}", file=sys.stderr)
        return 2

    results: list[tuple[str, str, str]] = []
    for label, kind, workload, expectation in ARMS:
        trace = os.path.join(HERE, f"sys_{label}.trace")
        shutil.rmtree(trace, ignore_errors=True)
        print(f"\n### {label}  ({kind}; {expectation})", flush=True)

        rec = subprocess.Popen(
            ["xcrun", "xctrace", "record", "--template", TEMPLATE, "--all-processes",
             "--time-limit", f"{args.seconds}s", "--output", trace],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, cwd=ROOT,
        )
        time.sleep(STARTUP_GRACE)
        if rec.poll() is not None:
            err = (rec.stderr.read() or "")[-500:] if rec.stderr else ""
            print(f"  RECORDING FAILED to start: {err}")
            results.append((label, "RECORD FAILED", expectation))
            continue

        t0 = time.time()
        run = subprocess.run(workload(), capture_output=True, text=True, cwd=ROOT)
        elapsed = time.time() - t0
        gate = ""
        for line in run.stdout.splitlines():
            if line.startswith("VERDICT") or line.startswith("warm median"):
                gate = line.strip()
        print(f"  workload {elapsed:.1f}s  {gate}")

        rec.wait()

        rep = subprocess.run(
            [sys.executable, os.path.join(HERE, "ane_report.py"), trace, label],
            capture_output=True, text=True, cwd=ROOT,
        )
        out = rep.stdout.strip()
        print("  " + out.replace("\n", "\n  "))
        intervals = "?"
        for line in out.splitlines():
            if "ANE intervals" in line:
                intervals = line.split(":")[1].strip()
        results.append((label, intervals, expectation))

        if not args.keep:
            shutil.rmtree(trace, ignore_errors=True)

    print("\n" + "=" * 78)
    print("SYSTEM-WIDE ANE CAPTURE")
    print("=" * 78)
    print(f"{'arm':<24}{'ANE intervals':>15}   expectation")
    for label, intervals, expectation in results:
        print(f"{label:<24}{intervals:>15}   {expectation}")

    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    d = {label: intervals for label, intervals, _ in results}

    def n(key: str) -> int:
        try:
            return int(d.get(key, "0"))
        except ValueError:
            return -1

    pos, neg_gpu, neg_cpu, question = n("minilm-ALL"), n("minilm-CPU_AND_GPU"), n("granite-cpuOnly"), n("granite-neuralEngine")
    if pos <= 0:
        print("  METHOD FAILED: system-wide capture saw no ANE even for the Core ML positive")
        print("  control (minilm-ALL). Recording is not observing ANE hardware -> void.")
        return 1
    if neg_gpu > 0 or neg_cpu > 0:
        print(f"  CAUTION: a negative control showed ANE activity (gpu={neg_gpu}, cpu={neg_cpu});")
        print("  background system activity is leaking into the measurement.")
    print(f"  positive control (Core ML, ALL)  : {pos} intervals  -> capture works")
    print(f"  negative controls                : gpu={neg_gpu}, cpuOnly={neg_cpu}")
    if question > 0:
        print(f"\n  RESULT: granite(.neuralEngine) shows {question} ANE intervals SYSTEM-WIDE.")
        print("  The Neural Engine DID execute the Core AI graph -- placement is proven.")
    else:
        print("\n  RESULT: granite(.neuralEngine) shows 0 ANE intervals system-wide, while the")
        print("  Core ML control shows activity. On this graph the .neuralEngine preference did")
        print("  NOT put work on the Neural Engine (silent fallback), OR Core AI's ANE path is")
        print("  not visible to ANE hardware counters. Power rails decide between those.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
