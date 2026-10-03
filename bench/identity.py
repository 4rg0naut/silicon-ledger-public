#!/usr/bin/env python3
"""identity.py — one machine identity, one schema, every probe.

Cross-chip fleet (M4 mini / M5 Max / iPad Air M2 and anything we bolt on later)
means probe outputs must be attributable to a machine without human memory.
Every tool that reports measurements emits this same key set:

    chip       sysctl machdep.cpu.brand_string (e.g. "Apple M5 Max")
    hw_model   sysctl hw.model                 (e.g. "Mac17,14")
    cores      physical CPU cores              (sysctl hw.physicalcpu)
    arch       uname -m                        (arm64)
    os         macOS product version           (sw_vers)
    os_build   macOS build                     (kern.osversion)

`identity()` returns a plain dict (JSON-safe). CLI:

    python3 bench/identity.py            # JSON to stdout
    python3 bench/identity.py --key chip # one value

iOS/tvOS hosts have no sysctl CLI; there, emit the same keys from the app and
leave unknown fields as null — declared, not guessed.
"""
from __future__ import annotations

import json
import platform
import subprocess
import sys


def _sysctl(name: str) -> str | None:
    try:
        out = subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def identity() -> dict:
    return {
        "chip": _sysctl("machdep.cpu.brand_string"),
        "hw_model": _sysctl("hw.model"),
        "cores": int(_sysctl("hw.physicalcpu") or 0) or None,
        "arch": platform.machine() or None,
        "os": platform.mac_ver()[0] or None,
        "os_build": _sysctl("kern.osversion"),
    }


def main(argv: list[str]) -> int:
    ident = identity()
    if len(argv) > 1 and argv[1] == "--key":
        if len(argv) != 3 or argv[2] not in ident:
            print(f"usage: --key {{{'|'.join(ident)}}}", file=sys.stderr)
            return 2
        print(ident[argv[2]])
        return 0
    print(json.dumps(ident, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
