"""Shared powermetrics rail parser — single source of truth for the power A/B
harnesses (power_ab.py, power_coreai.py, power_mlcore.py). If powermetrics
ever shifts rail label formatting, this is the one place that must change.
Unit rule: values are normalized to mW (powermetrics prints "X mW" or "X.YYY W"
depending on sampler version).

LOCALE RULE (2026-10-10): this box runs LANG=fr_FR.UTF-8 and Apple CLIs emit comma
decimals there (ps gave "9,1"; sysctl gave "3072,00M"). The old pattern `([\d.]+)`
therefore FAILED to match "1234,56 mW" and DROPPED the sample silently. The pattern now
accepts both separators and normalizes to a float. Harnesses should still export
LC_ALL=C; this is the belt to that braces."""

import re

POWER_RE = re.compile(r"(ANE|GPU|CPU|Combined)\s+Power[^:]*:\s*([\d.,]+)\s*(mW|W)")


def _num(s: str) -> float:
    """Accept "1234.56" and "1234,56" (fr locale); drop a thousands separator only
    when both separators appear (e.g. "1,234.56")."""
    if "," in s and "." in s:
        s = s.replace(",", "")
    return float(s.replace(",", "."))


def parse_power(text: str) -> dict[str, list[float]]:
    """Collect power samples in milliwatts, keyed by rail."""
    out: dict[str, list[float]] = {}
    for rail, value, unit in POWER_RE.findall(text):
        mw = _num(value) * (1000.0 if unit == "W" else 1.0)
        out.setdefault(rail, []).append(mw)
    return out
