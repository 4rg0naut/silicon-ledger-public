#!/usr/bin/env python3
"""registry.py — the instrument registry and its gate.

Why this exists (owner, 2026-10-10): after ~30 experiments there are hundreds of probes and
harnesses spread over five locations, and nothing recorded *which one is canonical*. LLM agents —
and humans — therefore re-derive them, and we duplicated real work (EXP-029 rebuilt a matmul2d
ladder and an energy wrapper that already existed as `bench/na_tiles.metal` and `bench/power_ab.py`).

This is the missing layer: PROCEDURAL memory. Facts live in the knowledge base / openclaims spine;
instruments live here. Instruments are deliberately NOT claims (they are an index of tools, not
statements about hardware), so this file is kept out of the claims pipeline.

Contract:
  * every script under the scanned locations MUST have an entry (path-stable)
  * every entry's path MUST still exist
  * entries carry: purpose, kind, status (canonical|duplicate|superseded|scratch|unclassified),
    the convention it follows, and where its evidence lives

usage:
  python3 tools/registry.py --check      # gate: exit 1 on unregistered tool or dead path
  python3 tools/registry.py --seed       # add entries for newly found files (status: unclassified)
  python3 tools/registry.py --view       # regenerate tools/TOOLS.md (human view)
  python3 tools/registry.py --unclassified   # list entries needing a status decision
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "tools" / "instruments.jsonl"
VIEW = ROOT / "tools" / "TOOLS.md"

# (glob, kind, scanned?) — paths are relative to ROOT; ".." reaches the super-repo.
LOCATIONS = [
    ("results/EXP-*/harness/*", "experiment-harness"),
    ("bench/*", "cross-experiment"),
    ("tools/*", "instrument"),
    ("evaluation/*", "evaluation"),
]
SCRATCH = [
    ("../work/*", "scratch"),
    ("../exp022-raw/*", "scratch"),
]
SOURCE_EXT = {".py", ".m", ".mm", ".c", ".h", ".metal", ".sh", ".swift", ".lldb", ".ps1", ".js", ".ts"}
SKIP_PART = {"__pycache__", ".dSYM", ".git", "node_modules", ".build", "repos"}
SKIP_NAME = {"instruments.jsonl", "TOOLS.md", "registry.py"}


def is_source(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in SOURCE_EXT and p.name not in SKIP_NAME \
        and not any(part in SKIP_PART for part in p.parts)


def purpose_of(p: Path) -> str:
    """First docstring line, or first meaningful comment line."""
    try:
        text = p.read_text(errors="replace")
    except Exception:
        return ""
    m = re.search(r'^\s*(?:"""|\'\'\')\s*(.+?)$', text, re.S | re.M)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()[:200]
    for line in text.splitlines()[:25]:
        s = line.strip()
        if s.startswith(("#", "//", "///", ";;")) and not s.startswith("#!"):
            body = re.sub(r"^[#/;]+ *", "", s)
            if len(body) > 8 and not body.lower().startswith(("copyright", "spdx")):
                return body[:200]
    return ""


def scan() -> dict[str, dict]:
    found: dict[str, dict] = {}
    for pattern, kind in LOCATIONS + SCRATCH:
        for p in sorted(ROOT.glob(pattern)):
            if not is_source(p):
                continue
            rel = os.path.relpath(p, ROOT)
            found[rel] = {"path": rel, "kind": kind, "purpose": purpose_of(p),
                          "bytes": p.stat().st_size}
    return found


def load() -> dict[str, dict]:
    if not REG.exists():
        return {}
    out = {}
    for line in REG.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["path"]] = r
    return out


def save(entries: dict[str, dict]) -> None:
    ordered = sorted(entries.values(), key=lambda r: r["path"])
    for i, r in enumerate(ordered, 1):
        r["id"] = f"INSTR-{i:03d}"
    REG.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in ordered))


def seed() -> int:
    entries, found = load(), scan()
    added = 0
    for rel, meta in found.items():
        if rel in entries:
            entries[rel].update({"kind": meta["kind"], "bytes": meta["bytes"]})
            if not entries[rel].get("purpose"):
                entries[rel]["purpose"] = meta["purpose"]
            continue
        entries[rel] = {"path": rel, "kind": meta["kind"], "bytes": meta["bytes"],
                        "purpose": meta["purpose"], "status": "unclassified",
                        "convention": "", "evidence": ""}
        added += 1
    save(entries)
    print(f"registry: {len(entries)} entries ({added} new, status=unclassified until classified)")
    return 0


def check() -> int:
    entries, found = load(), scan()
    missing = sorted(set(found) - set(entries))
    dead = sorted(p for p in entries if not (ROOT / p).exists() and entries[p]["kind"] != "scratch")
    unclassified = [r["id"] for r in entries.values() if r.get("status") == "unclassified"]
    if missing:
        print(f"FAIL: {len(missing)} instrument(s) on disk are NOT registered — run --seed, "
              f"then set status/convention (reuse the canonical one, or say why it is new):")
        for p in missing[:20]:
            print(f"  {p}")
    if dead:
        print(f"FAIL: {len(dead)} registry entr(y|ies) point at a missing path:")
        for p in dead[:20]:
            print(f"  {p}")
    if unclassified:
        print(f"WARN: {len(unclassified)} entr(y|ies) still unclassified (status TODO): "
              f"{' '.join(unclassified[:12])}{' …' if len(unclassified) > 12 else ''}")
    if not missing and not dead:
        print(f"registry OK: {len(found)} instruments on disk, {len(entries)} registered, "
              f"{len(unclassified)} unclassified")
        return 0
    return 1


def view() -> int:
    entries = load()
    lines = ["# Instrument registry (generated by tools/registry.py --view — do not hand-edit)",
             "",
             "Facts live in `knowledge/ane/`; **instruments live here**. Read this before writing any",
             "new probe: if a canonical instrument exists, reuse it. Add an entry when you add a tool.",
             "",
             "Status: **canonical** = the one to use · **duplicate** = exists, prefer its canonical "
             "twin · **superseded** = kept only as an evidence artifact · **unclassified** = TODO.",
             ""]
    for kind in ("cross-experiment", "instrument", "experiment-harness", "evaluation", "scratch"):
        rows = [r for r in entries.values() if r["kind"] == kind]
        if not rows:
            continue
        lines += [f"## {kind} ({len(rows)})", "", "| id | path | status | purpose |", "|---|---|---|---|"]
        for r in sorted(rows, key=lambda r: (r.get("status", ""), r["path"])):
            lines.append(f"| {r['id']} | `{r['path']}` | {r.get('status','?')} | "
                         f"{(r.get('purpose') or '')[:110]} |")
        lines.append("")
    VIEW.write_text("\n".join(lines) + "\n")
    print(f"wrote {os.path.relpath(VIEW, ROOT)} ({len(entries)} entries)")
    return 0


# --- capability map -------------------------------------------------------------------------
# path -> (status, canonical_for, convention/notes). This is the part that is MEMORY: it answers
# "which instrument do I use for X?" without re-deriving it. Keep it small and decisive.
CANON = {
    "tools/kb_pipeline.sh": ("canonical", "gates/pipeline",
        "THE standard gate set: registry -> records -> validate -> spine append -> spine check"),
    "tools/registry.py": ("canonical", "instrument registry + gate", "this file; --check is step 1 of the pipeline"),
    "bench/latency_protocol.py": ("canonical", "timing/latency",
        "warm-up 10 discarded / measured 100 back-to-back / report p50,p95,min + ms-per-token / state the work unit"),
    "bench/power_ab.py": ("canonical", "joules (powermetrics)", "sudo window; whole-system rails"),
    "bench/_power.py": ("canonical", "joules parser", "single source of truth for rail parsing; locale-safe"),
    "bench/power_coreai.py": ("canonical", "joules (Core AI arm)", "uses _power.py"),
    "bench/power_mlcore.py": ("canonical", "joules (MLCompute arm)", "uses _power.py"),
    "tools/enginemon/enginemon.c": ("canonical", "lane activity (unprivileged)",
        "ANEXL U = ANE-exclusive; GPU Energy; PS13 is generic GPU, not NAX"),
    "bench/na_tiles.py": ("canonical", "matmul2d tile probe (original)", "the ancestor EXP-027 borrowed"),
    "bench/na_tiles.metal": ("canonical", "matmul2d tile kernel (original)", "known-to-compile MSL"),
    "results/EXP-027-nax/harness/p27_r8.m": ("canonical", "matmul2d multi-tile ladder + CPU oracle",
        "threadgroup staging + cooperative destination; the correctness-gated ladder"),
    "results/EXP-027-nax/harness/p27_na_r8.py": ("canonical", "matmul2d ladder (coreai route)", "validity-only, no timing"),
    "results/EXP-025-ane-gpu-sync/harness/plan_devicesupport.m": ("canonical", "Core ML placement + device support info", ""),
    "results/EXP-025-ane-gpu-sync/harness/coreml_plan.py": ("canonical", "Core ML placement (python)", ""),
    "results/EXP-025-ane-gpu-sync/harness/coreml_route_sweep.py": ("canonical", "placement decision table sweep", ""),
    "results/EXP-025-ane-gpu-sync/harness/coreml_findcallers.m": ("canonical", "reverse references in the loaded CoreML image", ""),
    "bench/build_measurements.py": ("canonical", "ledger build", "only sanctioned way into measurements.json"),
    "bench/results_table.py": ("canonical", "ledger summary", "generated SUMMARY.md"),
    "bench/verify_extraction.py": ("canonical", "ledger gate", "value must literally appear in its source"),
    "bench/audit_measurements.py": ("canonical", "ledger re-check", ""),
    "results/EXP-029-nax-crosslane/harness/quiet_probe.sh": ("canonical", "measurement-window gate (contention)",
        "GPU idle band + daemon watchlist before/after"),
    "results/EXP-029-nax-crosslane/harness/canary.c": ("canonical", "machine-state canary",
        "build -O0; -O2 deletes the loops"),
    "bench/interference_coreai.py": ("canonical", "interference (Core AI)", ""),
    "bench/calibration_axis.py": ("canonical", "attribution-lens calibration", ""),
    "results/EXP-029-nax-crosslane/harness/nax_gemm/main.swift": ("canonical", "GPU GEMM probe (MetalHLO, dtype-controlled, MLX-free)",
        "NEW content: MetalHLO runner has no f16 cells and always runs MLX; adopt latency_protocol conventions"),
    "results/EXP-029-nax-crosslane/harness/ane_gemm_probe.py": ("canonical", "ANE GEMM probe (lane + time + error)",
        "NEW content; adopt latency_protocol conventions"),
    "results/EXP-029-nax-crosslane/harness/make_gemm_models.py": ("canonical", "GEMM model builder (matmul vs 1x1-conv forms)", ""),
    "results/EXP-029-nax-crosslane/harness/nax_gemm_energy.sh": ("canonical", "lane attribution during a workload (unprivileged)",
        "enginemon-based; NOT a joule source - use power_ab.py for joules"),
    "results/EXP-029-nax-crosslane/harness/ane_gemm_energy.sh": ("canonical", "ANE activity + GPU energy during a CoreML run",
        "enginemon-based; ANE joules need the sudo powermetrics window"),
}
DUPES = {
    "results/EXP-029-nax-crosslane/harness/nax_ladder.m": ("superseded", "matmul2d ladder",
        "duplicate of bench/na_tiles.metal + p27_r8.m; kept as an artifact of the 2026-10-10 investigation"),
    "results/EXP-029-nax-crosslane/harness/mm_inline.metal": ("superseded", "MPP compile probe",
        "compile-only probe; superseded by MetalHLO as the working MPP route"),
    "results/EXP-029-nax-crosslane/harness/nax_gemm_matrix.sh": ("duplicate", "GPU lane matrix",
        "MetalHLO's own runner covers the arm A/B; ours adds dtype/MLX-free angles only"),
    "results/EXP-029-nax-crosslane/harness/nax_lane_matrix.sh": ("duplicate", "GPU lane matrix",
        "same as above - the runner's --filter already does this"),
}


def classify() -> int:
    entries = load()
    hit = 0
    for path, (status, for_, note) in {**CANON, **DUPES}.items():
        if path in entries:
            entries[path].update({"status": status, "canonical_for": for_, "convention": note})
            hit += 1
    save(entries)
    print(f"classified {hit} instrument(s) from the capability map")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--view", action="store_true")
    ap.add_argument("--unclassified", action="store_true")
    ap.add_argument("--classify", action="store_true")
    a = ap.parse_args()
    if a.seed:
        return seed()
    if a.view:
        return view()
    if a.classify:
        return classify()
    if a.unclassified:
        for r in load().values():
            if r.get("status") == "unclassified":
                print(f"{r['id']}  {r['path']}  — {r.get('purpose','')[:90]}")
        return 0
    return check()          # default: gate


if __name__ == "__main__":
    sys.exit(main())
