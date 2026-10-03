#!/usr/bin/env python3
"""Does ANE power drop when the ANE slows down? — the burst/sustained discriminator.

EXP-005 step 7 established two ANE throughput states (~31 GB/s burst vs ~14.5 GB/s sustained,
latency 1.9 ms vs 4.75 ms) with an unidentified cause. Two candidates remain:

  (a) a CLOCK/POWER state change — the engine runs slower *and* draws less power;
  (b) a BANDWIDTH ceiling — the engine works just as hard but moves less data per second.

These are separable by one number: ANE power before vs after the transition.

  power falls with the slowdown  -> (a) clock/power state
  power stays flat              -> (b) bandwidth ceiling

enginemon cannot answer this: its `Energy Model -> ANE` channel is frozen (F-24), and the only
working power channel it sees is `GPU Energy`. So this uses `powermetrics`, which needs root.

It samples at 200 ms while the runner performs a long ANE run with its per-inference latency
series dumped, then splits the power samples at the measured transition index and reports both
windows.

usage:  cd "$(git rev-parse --show-toplevel)"
        sudo .venv/bin/python bench/power_phase_probe.py --iters 4000
"""

from __future__ import annotations

import argparse
import os
import re
import statistics as st
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "tools/granite-runner/.build/out/Products/Release/granite-runner"
B = ROOT / "models/granite97m/macos/fp32-s128"
BUNDLE = ROOT / "work/exports/granite-embedding-97m/ane-sweep/v3/aot/granite97m_fp16_s128_v3.h16g.aimodelc"

# NOTE: an earlier version of this file parsed per-sample blocks with its own regexes and
# silently dropped most samples (14 parsed out of ~51 expected), producing fields that did not
# match power_coreai.py's readings for the same workload. It now uses the same validated
# parser (power_ab.parse_power) and writes the raw log, so any disagreement is checkable.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from power_ab import parse_power  # noqa: E402


def parse_samples(raw: str) -> list[tuple[int, int, int]]:
    """(cpu, gpu, ane) mW triples, aligned by index from the whole-text parser."""
    rails = parse_power(raw)
    n = min(len(rails.get("CPU", [])), len(rails.get("GPU", [])), len(rails.get("ANE", [])))
    return [(int(rails["CPU"][i]), int(rails["GPU"][i]), int(rails["ANE"][i])) for i in range(n)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=4000)
    ap.add_argument("--interval", type=int, default=200)
    ap.add_argument("--samples", type=int, default=400,
                    help="powermetrics -n (bounded; it must exit on its own to flush)")
    args = ap.parse_args()

    try:
        import json as _json
        from identity import identity
        print(f"  identity: {_json.dumps(identity(), separators=(',', ':'))}")
    except Exception as e:
        print(f"  identity: unavailable ({e})", file=sys.stderr)

    if os.geteuid() != 0:
        print("powermetrics needs root:  sudo .venv/bin/python bench/power_phase_probe.py", file=sys.stderr)
        return 2
    for p in (BIN, BUNDLE):
        if not p.exists():
            print(f"missing {p}", file=sys.stderr)
            return 2

    lat = ROOT / "work" / "lat" / "power_phase.txt"
    lat.parent.mkdir(parents=True, exist_ok=True)
    lat.unlink(missing_ok=True)

    # NOTE: `-n` (a bounded sample count) with a natural exit is required. Terminating
    # powermetrics loses most of its buffered output: an earlier version produced 14 samples
    # for a 13.8 s run at -i 200 (~1 Hz instead of 5 Hz), which silently truncated the series.
    # We over-provision the count and let it finish on its own.
    budget_s = args.interval / 1000.0 * args.samples
    pm = subprocess.Popen(["powermetrics", "--samplers", "ane_power,gpu_power,cpu_power",
                           "-i", str(args.interval), "-n", str(args.samples)],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(2.0)  # let the sampler settle
    t0 = time.perf_counter()
    run = subprocess.run([str(BIN), str(BUNDLE), str(B / "tokenizer"), str(B / "reference.json"),
                          "--compute", "neuralEngine", "--iters", str(args.iters),
                          "--dump-latencies", str(lat)],
                         capture_output=True, text=True)
    elapsed = time.perf_counter() - t0
    try:
        raw = pm.communicate(timeout=budget_s + 30)[0]   # exits after `samples` samples
    except subprocess.TimeoutExpired:
        pm.kill()
        raw = pm.communicate()[0]

    rawlog = ROOT / "work" / "lat" / "power_phase_raw.txt"
    rawlog.parent.mkdir(parents=True, exist_ok=True)
    rawlog.write_text(raw or "")
    samples = parse_samples(raw or "")
    print(f"raw powermetrics log: {rawlog}")
    xs = [float(l) for l in lat.read_text().splitlines() if l.strip()] if lat.exists() else []

    expected = elapsed / (args.interval / 1000.0)
    print(f"runner: {elapsed:.1f}s, {args.iters} iters, {len(samples)} power samples @ {args.interval} ms"
          f" (expected ~{expected:.0f} — a large shortfall means output was lost)")
    for line in run.stdout.splitlines():
        if "warm median" in line or "VERDICT" in line:
            print(f"  {line.strip()}")

    if not samples or not xs:
        print("no samples captured")
        return 1

    # locate the transition in the latency series
    fast_idx = [i for i, v in enumerate(xs) if v < 3.0]
    trans = (max(fast_idx) + 1) if fast_idx else 0
    print(f"\nlatency series: {len(xs)} samples, fast phase {trans} "
          f"({100*trans/len(xs):.0f}%)")

    # map the transition index to a time, then split the power samples
    per_iter = elapsed / len(xs)
    t_trans = trans * per_iter
    split = int(t_trans / (args.interval / 1000.0))
    split = max(1, min(split, len(samples) - 1))
    before, after = samples[:split], samples[split:]

    print(f"\ntransition at sample ~{split} of {len(samples)} power samples "
          f"(~{t_trans:.1f}s into the run)\n")
    print(f"{'window':<26}{'n':>4}{'CPU mW':>10}{'GPU mW':>10}{'ANE mW':>10}")
    for label, win in (("burst phase (before)", before), ("sustained phase (after)", after)):
        if not win:
            continue
        cpu = st.mean(s[0] for s in win)
        gpu = st.mean(s[1] for s in win)
        ane = st.mean(s[2] for s in win)
        print(f"{label:<26}{len(win):>4}{cpu:>10.0f}{gpu:>10.0f}{ane:>10.0f}")

    if before and after and len(before) >= 3 and len(after) >= 3:
        a0 = st.mean(s[2] for s in before)
        a1 = st.mean(s[2] for s in after)
        print(f"\nANE power ratio sustained/burst = {a1/a0:.2f}" if a0 else "\nANE power ~0 in both windows")
        print()
        if a0 and a1 and a1 < 0.7 * a0:
            print("  => ANE power FALLS with the slowdown: a clock/power state change (DVFS-like).")
        elif a0 and a1 and a1 > 0.9 * a0:
            print("  => ANE power is FLAT while throughput halves: a bandwidth ceiling, not a clock drop.")
        else:
            print("  => intermediate: partial power reduction; inspect the series below.")
    else:
        print("  => NO VERDICT: one window has fewer than 3 samples, so the run did not")
        print("     capture a transition. Re-run; the state varies over the session.")
    print("\nper-sample series (CPU, GPU, ANE mW):")
    for i, s in enumerate(samples):
        mark = " <-- transition" if i == split else ""
        print(f"  {i:>3}  {s[0]:>6} {s[1]:>6} {s[2]:>6}{mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
