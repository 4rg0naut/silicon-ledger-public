#!/usr/bin/env python3
"""Summarise ANE hardware activity from an xctrace recording.

Reads the `ane-hw-intervals` table ("Denotes an interesting period of activity
in the ANE") and reports how many intervals occurred and how long the ANE was
busy in total. This is the empirical answer to "did the Neural Engine actually
do the work?".

Usage: python3 ane_report.py <trace> [label]
"""
from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ET

XPATH = '/trace-toc/run[@number="1"]/data/table[@schema="ane-hw-intervals"]'


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    trace = sys.argv[1]
    label = sys.argv[2] if len(sys.argv) > 2 else trace

    proc = subprocess.run(
        ["xcrun", "xctrace", "export", "--input", trace, "--xpath", XPATH],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        print(f"{label}: export failed -> {proc.stderr.strip()[:120]}")
        return 1

    try:
        root = ET.fromstring(proc.stdout)
    except ET.ParseError as exc:
        print(f"{label}: unparsable export ({exc})")
        return 1

    rows = root.findall(".//row")
    total_ns = 0
    durations_ns: list[int] = []
    labels: set[str] = set()
    for row in rows:
        dur = row.find("duration")
        if dur is None or not dur.text:
            continue
        try:
            ns = int(dur.text)
        except ValueError:
            continue
        durations_ns.append(ns)
        total_ns += ns
        for el in row:
            if el.get("fmt") and "Prediction" in (el.get("fmt") or ""):
                labels.add("Neural Engine Prediction")

    total_ms = total_ns / 1e6
    print(f"=== {label} ===")
    print(f"  ANE intervals      : {len(durations_ns)}")
    print(f"  ANE busy (total)   : {total_ms:.2f} ms")
    if durations_ns:
        print(f"  longest interval   : {max(durations_ns)/1e6:.2f} ms")
        print(f"  mean interval      : {sum(durations_ns)/len(durations_ns)/1e6:.2f} ms")
    if labels:
        print(f"  labels seen        : {', '.join(sorted(labels))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
