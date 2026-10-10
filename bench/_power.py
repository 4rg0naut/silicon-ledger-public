"""Shared powermetrics rail parser — single source of truth for the power A/B
harnesses (power_ab.py, power_coreai.py, power_mlcore.py). If powermetrics
ever shifts rail label formatting, this is the one place that must change.
Unit rule: values are normalized to mW (powermetrics prints "X mW" or "X.YYY W"
depending on sampler version)."""

import re

POWER_RE = re.compile(r"(ANE|GPU|CPU|Combined)\s+Power[^:]*:\s*([\d.]+)\s*(mW|W)")


def parse_power(text: str) -> dict[str, list[float]]:
    """Collect power samples in milliwatts, keyed by rail."""
    out: dict[str, list[float]] = {}
    for rail, value, unit in POWER_RE.findall(text):
        mw = float(value) * (1000.0 if unit == "W" else 1.0)
        out.setdefault(rail, []).append(mw)
    return out
