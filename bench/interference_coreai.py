#!/usr/bin/env python3
"""Differential placement test for a Core AI graph -- accelerator contention.

WHY THIS EXISTS
---------------
xctrace's `ane-hw-intervals` reports NOTHING for Core AI graphs (a Core ML control in the
same session shows 269 intervals), and the Core AI API exposes no "which unit did you
actually use" getter (checked: CoreAI.tbd, CoreAIKitVision). `preferredComputeUnitKind`
is a *preference*, so it can silently fall back.

So placement is inferred from CONTENTION between two processes:

  If granite(.neuralEngine) runs on the ANE, a concurrent ANE-saturating load must slow
  it down -- while a concurrent load that uses CPU+GPU but NOT the ANE must not.

HOGS (Core ML, via bench_encoder.py --only):
  CPU_AND_GPU -> saturates CPU+GPU, provably cannot use the ANE
  ALL         -> CPU+GPU+ANE   (EXP-003: 269 ANE intervals -- proven)
The ONLY difference between the two hogs is ANE participation. A slowdown that appears
under ALL but not under CPU_AND_GPU is therefore attributable to ANE contention.

POSITIVE CONTROL
  granite(.gpu) MUST slow under CPU_AND_GPU. If it does not, the method cannot detect
  contention at all and every other result is void.

usage: .venv/bin/python bench/interference_coreai.py [--iters 2000] [--hog-iters 300000]
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

BIN = os.path.join(ROOT, "tools/granite-runner/.build/out/Products/Release/granite-runner")
BUNDLE = os.path.join(ROOT, "models/granite97m/macos/fp32-s128/granite97m_fp32_s128_bound.aimodel")
TOKENIZER = os.path.join(ROOT, "models/granite97m/macos/fp32-s128/tokenizer")
REFERENCE = os.path.join(ROOT, "models/granite97m/macos/fp32-s128/reference.json")
ENCODER = os.path.join(HERE, "bench_encoder.py")

MEDIAN_RE = re.compile(r"median_ms=([\d.]+)")
GATE_RE = re.compile(r"gate=(PASS|FAIL)")


def run_granite(compute: str, iters: int) -> tuple[float, str]:
    """One granite run; returns (median_ms, gate)."""
    p = subprocess.run(
        [BIN, BUNDLE, TOKENIZER, REFERENCE, "--compute", compute, "--iters", str(iters)],
        capture_output=True, text=True, cwd=ROOT,
    )
    if p.returncode != 0:
        raise RuntimeError(f"granite failed ({compute}): {p.returncode}\n{p.stderr[-800:]}")
    m, g = MEDIAN_RE.search(p.stdout), GATE_RE.search(p.stdout)
    if not m or not g:
        raise RuntimeError(f"unparsable granite output:\n{p.stdout[-800:]}")
    return float(m.group(1)), g.group(1)


class Hog:
    """A Core ML encoder looping on a fixed compute-unit set, as background load."""

    def __init__(self, unit: str, iters: int):
        self.unit = unit
        self.proc = subprocess.Popen(
            [sys.executable, ENCODER, "--only", unit, "--iters", str(iters)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=ROOT,
        )

    def __enter__(self) -> "Hog":
        time.sleep(3.0)  # let Core ML compile + start saturating
        if self.proc.poll() is not None:
            raise RuntimeError(f"hog {self.unit} died during startup")
        return self

    def alive(self) -> bool:
        return self.proc.poll() is None

    def __exit__(self, *exc) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=2000, help="granite inferences per arm")
    ap.add_argument("--hog-iters", type=int, default=300000, help="hog inferences (killed early)")
    args = ap.parse_args()

    for path in (BIN, BUNDLE, TOKENIZER, REFERENCE, ENCODER):
        if not os.path.exists(path):
            print(f"missing: {path}", file=sys.stderr)
            return 2

    print("granite runner + Core ML hogs, same machine, same session")
    print(f"granite iters/arm: {args.iters}   hog iters: {args.hog_iters}\n")

    arms: list[tuple[str, str, float, str]] = []  # (hog, granite compute, median, gate)

    # ---- no hog: baselines -------------------------------------------------
    for cu in ("neuralEngine", "gpu"):
        med, gate = run_granite(cu, args.iters)
        arms.append(("none", cu, med, gate))
        print(f"  [no hog]        granite({cu:<12}) {med:8.3f} ms  gate={gate}")

    # ---- hogs --------------------------------------------------------------
    for hog_unit in ("CPU_AND_GPU", "ALL"):
        with Hog(hog_unit, args.hog_iters) as hog:
            print(f"\n  [hog {hog_unit}] -- saturating")
            for cu in ("neuralEngine", "gpu"):
                med, gate = run_granite(cu, args.iters)
                arms.append((hog_unit, cu, med, gate))
                alive = "" if hog.alive() else "  ** HOG DIED EARLY **"
                print(f"  [{hog_unit:<11}] granite({cu:<12}) {med:8.3f} ms  gate={gate}{alive}")

    # ---- report ------------------------------------------------------------
    base = {cu: med for hog, cu, med, _ in arms if hog == "none"}

    print("\n" + "=" * 74)
    print("CONTENTION MATRIX  (slowdown vs no-hog baseline)")
    print("=" * 74)
    print(f"{'granite compute':<16}{'baseline':>10}{'hog CPU+GPU':>14}{'hog ALL(+ANE)':>15}")
    for cu in ("neuralEngine", "gpu"):
        row = {hog: med for hog, c, med, _ in arms if c == cu}
        b = base[cu]
        g = row.get("CPU_AND_GPU", float("nan"))
        a = row.get("ALL", float("nan"))
        print(f"{cu:<16}{b:>10.3f}{g:>14.3f}{a:>15.3f}   (ms)")

    print("\n" + "=" * 74)
    print("VERDICT")
    print("=" * 74)
    gpu_base = base["gpu"]
    gpu_hog = {hog: med for hog, c, med, _ in arms if c == "gpu"}.get("CPU_AND_GPU", float("nan"))
    ne_base = base["neuralEngine"]
    ne_cg = {hog: med for hog, c, med, _ in arms if c == "neuralEngine"}.get("CPU_AND_GPU", float("nan"))
    ne_all = {hog: med for hog, c, med, _ in arms if c == "neuralEngine"}.get("ALL", float("nan"))

    ane_slow = ne_all / ne_base
    gpu_slow = ne_cg / ne_base
    ctrl = gpu_hog / gpu_base

    print(f"  control  granite(gpu)          under CPU+GPU hog : {ctrl:5.2f}x")
    print(f"           granite(neuralEngine) under CPU+GPU hog : {gpu_slow:5.2f}x")
    print(f"           granite(neuralEngine) under ALL     hog : {ane_slow:5.2f}x")

    if ctrl < 1.15:
        print("\n  METHOD FAILED: granite(gpu) did not slow under a GPU hog -- this machine's")
        print("  GPU contention is not observable this way. All other rows are void.")
        return 1

    print()
    if ane_slow > 1.15 and gpu_slow < 1.15:
        print("  RESULT: granite(.neuralEngine) is slowed by an ANE-saturating load and NOT by")
        print("  a GPU-only load  =>  the graph IS running on the Neural Engine.")
    elif gpu_slow > 1.15 and ane_slow > 1.15:
        print("  RESULT: granite(.neuralEngine) is slowed by a load that cannot use the ANE  =>")
        print("  the preference FELL BACK (CPU/GPU), it is NOT on the Neural Engine.")
    else:
        print("  RESULT: INCONCLUSIVE -- granite(.neuralEngine) is not measurably contended by")
        print("  either hog (latency may be overhead-bound rather than accelerator-bound).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
