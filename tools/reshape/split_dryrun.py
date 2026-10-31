#!/usr/bin/env python3
"""split_dryrun.py — dry-run report for splitting the ports project's CODE out of the ledger.

Nothing is moved. The script classifies every tracked file as MOVE or STAY (rules below), then
reports what a split would break: instruments that move, references from staying files to moving
paths (split by kind), code-level dependencies in both directions, and a go/no-go verdict.

usage:
  python3 tools/reshape/split_dryrun.py [--repo PATH] [--out docs/reshape/SPLIT-DRYRUN.md]
  --repo defaults to the repo containing this script; point it at a throwaway clone to rehearse.
Evidence (results/EXP-*) always STAYS: the ledger rows and spine reference it by path.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

MOVE_DIRS = ("ports/", "evaluation/", "contrib/", "tools/embed-server/", "tools/rerank-server/",
             "tools/memory-stack/")
MOVE_BENCH = (
    "mteb_french_tasks.py", "mteb_interface.py", "mteb_multilingual_refs.py", "mteb_reference.py",
    "mteb_retrieval.py", "mteb_taskinfo.py", "von_authored144.py", "train_decision_model.py",
    "compare_retrievers.py", "rerank_retrieval.py", "chunk_indexed_retrieval.py",
    "eval_ane_embedder.py", "eval_dev_calibration.py", "convert_reranker.py",
    "gate_precision_report.py", "losses.py", "aot_verify.sh",
)
# D-07 (2026-10-30, owner): lane-primary tools stay even when ports-era. The old list carried
# bench_encoder / granite_ane_variants / jevbench_ane / laya_ane_bench / classify_unit_kind /
# gate_reranker_ane / correctness_head / granite-runner / the compiler-RE repros — every one of
# them measures the silicon, not the model.
# Provenance/config strings naming a moving path are pointers, not calls (2026-10 audit):
# build_measurements' row table, publish.sh's KEEP lists, registry.py's LOCATIONS globs.
POINTER_FILES = ("bench/build_measurements.py", "tools/publish/publish.sh", "tools/registry.py")
TEXT_EXT = {".md", ".json", ".jsonl", ".py", ".sh", ".txt", ".tsv", ".m", ".c", ".h", ".metal",
            ".swift", ".ndjson", ".yml", ".yaml", ".toml"}
DIR_TOKENS = {"ports/": r"(?<![\w.\-])ports/", "evaluation/": r"(?<![\w.\-])evaluation/",
              "contrib/": r"(?<![\w.\-])contrib/", "tools/embed-server/": r"embed-server",
              "tools/rerank-server/": r"rerank-server", "tools/memory-stack/": r"(?<![\w.\-])tools/memory-stack"}
# (D-07: the old bare token also matched the gitignored SCRATCH path work/memory-stack — that is
# not a reference to the moving tools/memory-stack package; its migration is phase 4F.)


def git_files(repo: Path) -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


def is_move(f: str) -> bool:
    if f.startswith(MOVE_DIRS):
        return True
    return f.startswith("bench/") and f.count("/") == 1 and f.split("/")[1] in MOVE_BENCH


def kind_of(f: str) -> str:
    if f.startswith("knowledge/ane/openclaims/") or f.startswith("knowledge/ane/records/"):
        return "spine/records"
    if f == "results/measurements.json":
        return "measurements.json"
    if f.startswith("knowledge/"):
        return "knowledge prose"
    if f.startswith("results/") and f.endswith(".md"):
        return "results prose"
    if f.startswith("results/"):
        return "results data/harness"
    if f.endswith((".py", ".sh", ".m", ".c", ".swift", ".metal", ".h")):
        return "code"
    return "other prose/config"


def reference_tokens(f: str) -> list[tuple[str, re.Pattern]]:
    if f.startswith("bench/"):
        base = f.split("/")[1]
        return [(f"bench/{base}", re.compile(r"(?<![\w.\-])" + re.escape(base) + r"(?![\w\-])"))]
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--out", default="docs/reshape/SPLIT-DRYRUN.md")
    a = ap.parse_args()
    repo = Path(a.repo).resolve()
    out_path = Path(a.out)
    if not out_path.is_absolute():
        out_path = Path(__file__).resolve().parents[2] / out_path

    files = git_files(repo)
    moving = sorted(f for f in files if is_move(f))
    staying = [f for f in files if not is_move(f)]
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo, capture_output=True,
                          text=True).stdout.strip()

    top = Counter(f.split("/")[0] for f in moving)
    move_bytes = sum((repo / f).stat().st_size for f in moving if (repo / f).exists())

    instr = [json.loads(l) for l in (repo / "tools/instruments.jsonl").read_text().splitlines() if l.strip()]
    moving_instr = [r for r in instr if r["path"] in set(moving)]
    stay_instr_paths = {r["path"] for r in instr if r["path"] not in set(moving)}

    tokens: dict[str, list[str]] = defaultdict(list)
    patterns: list[tuple[str, re.Pattern]] = []
    for d, rx in DIR_TOKENS.items():
        patterns.append((d, re.compile(rx)))
    for f in moving:
        if f.startswith("bench/"):
            patterns.append(reference_tokens(f)[0])

    refs: dict[str, Counter] = defaultdict(Counter)
    ref_examples: dict[str, list[str]] = defaultdict(list)
    code_deps: list[tuple[str, str]] = []
    for f in staying:
        p = repo / f
        if p.suffix.lower() not in TEXT_EXT or not p.is_file():
            continue
        try:
            text = p.read_text(errors="replace")
        except Exception:
            continue
        k = kind_of(f)
        for label, rx in patterns:
            n = len(rx.findall(text))
            if n:
                refs[k][label] += n
                if len(ref_examples[k]) < 6 and f not in ref_examples[k]:
                    ref_examples[k].append(f"{f} -> {label}")
                if k == "code" or (k == "results data/harness" and p.suffix in {".py", ".sh", ".m", ".c", ".swift"}):
                    code_deps.append((f, label))

    move_modules = {Path(f).stem: f for f in moving if f.startswith("bench/") and f.endswith(".py")}
    stay_modules = {Path(f).stem: f for f in staying if f.startswith("bench/") and f.endswith(".py")}
    py_blockers, py_reverse = [], []
    for f in staying:
        if f.endswith(".py") and (repo / f).is_file():
            try:
                tree = ast.parse((repo / f).read_text(errors="replace"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [n.name.split(".")[0] for n in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    names = [node.module.split(".")[0]]
                for n in names:
                    if n in move_modules:
                        py_blockers.append((f, move_modules[n]))
    for f in moving:
        if f.endswith(".py") and (repo / f).is_file():
            try:
                tree = ast.parse((repo / f).read_text(errors="replace"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [n.name.split(".")[0] for n in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    names = [node.module.split(".")[0]]
                for n in names:
                    if n in stay_modules:
                        py_reverse.append((f, stay_modules[n]))
    py_blockers = sorted(set(py_blockers))
    py_reverse = sorted(set(py_reverse))

    live_code_deps = sorted({(f, l) for f, l in code_deps
                             if not f.startswith(("results/EXP-00", "results/EXP-01", "results/EXP-020",
                                                  "results/EXP-021", "results/EXP-022", "results/EXP-023"))})
    legacy_code_deps = sorted({(f, l) for f, l in code_deps} - set(live_code_deps))
    blockers_code = sorted({(f, l) for f, l in live_code_deps}) + [(f, f"import {t}") for f, t in py_blockers]
    blocking_files = sorted({f for f, _ in blockers_code
                             if not f.startswith(("tools/audit/", "tools/reshape/"))
                             and f not in POINTER_FILES})
    pointer_hits = sorted({(f, l) for f, l in blockers_code if f in POINTER_FILES})

    L = []
    w = L.append
    w("# Split dry-run — ports project code out of silicon-ledger")
    w("")
    w(f"Generated by `tools/reshape/split_dryrun.py` against commit `{head}`. Nothing was moved. Rebuild, never patch.")
    w("")
    w("Scope: CODE only (see `DECISIONS.md`). `results/EXP-*` (evidence), ledger rows and the spine stay in this repo.")
    w("")
    w("## 1. What would move")
    w("")
    w(f"{len(moving)} of {len(files)} tracked files, {move_bytes/1024:.0f} KiB.")
    w("")
    w("| top dir | files |")
    w("|---|---|")
    for k, v in sorted(top.items()):
        w(f"| `{k}` | {v} |")
    w("")
    w("### Full file list")
    w("")
    for f in moving:
        w(f"- `{f}`")
    w("")
    w("## 2. Instruments that would move")
    w("")
    w(f"{len(moving_instr)} of {len(instr)} registry entries (`tools/instruments.jsonl`). The registry gate would have to learn that these ids live in the other repo (ids are append-only and cited; they must not be renumbered).")
    w("")
    w("| id | path | status |")
    w("|---|---|---|")
    for r in sorted(moving_instr, key=lambda r: r["id"]):
        w(f"| {r['id']} | `{r['path']}` | {r.get('status','?')} |")
    w("")
    w("## 3. References from staying files that would dangle")
    w("")
    w("Counted by pattern match on staying text files; every hit becomes a pointer that must be rewritten to the new repo (or kept as prose).")
    w("")
    total_refs = sum(sum(c.values()) for c in refs.values())
    w(f"Total hits: **{total_refs}** across {len(refs)} file kinds.")
    w("")
    w("| file kind | hits | distinct targets | examples |")
    w("|---|---|---|---|")
    for k in sorted(refs):
        c = refs[k]
        ex = "; ".join(ref_examples[k][:3])
        w(f"| {k} | {sum(c.values())} | {len(c)} | {ex} |")
    w("")
    sp = refs.get("spine/records", Counter())
    mj = refs.get("measurements.json", Counter())
    w(f"- Spine/records (append-only, cannot be edited in place): {sum(sp.values())} hits. Corrections would be NEW records with the move in the caveat.")
    w(f"- `measurements.json`: {sum(mj.values())} hits (mostly `command` fields naming bench scripts).")
    w("")
    w("## 4. Code dependencies")
    w("")
    w("### 4a. Staying code that calls into moving code (BLOCKING until resolved)")
    w("")
    w("Census/listing tools (`tools/audit/`, `tools/reshape/`), `measurements.json` command strings and docstring mentions are NOT calls and are counted in section 3 instead. Provenance/config strings in staying code (`bench/build_measurements.py` row table, `tools/publish/publish.sh` KEEP lists, `tools/registry.py` LOCATIONS — see `DECISIONS.md` D-07) are historical pointers, not calls; they are listed in 4a-ptr below and resolved by rewording the path to point at the other repo, not by a code change. What remains here is staying code that actually runs moving code.")
    w("")
    NONCALL = ("tools/audit/", "tools/reshape/")
    by_target: dict[str, set] = defaultdict(set)
    for f, l in blockers_code:
        if f.startswith(NONCALL) or f in POINTER_FILES:
            continue
        by_target[l].add(f)
    if by_target:
        w("| moving target | staying callers | suggested resolution |")
        w("|---|---|---|")
        for t in sorted(by_target):
            callers = sorted(by_target[t])
            live = [c for c in callers if c.startswith(("bench/", "tools/"))]
            if t.startswith(("tools/granite-runner", "import bench/")) or (t.startswith("bench/") and live):
                res = "keep in ledger (live instrument path) or extract as shared package"
            elif t == "tools/memory-stack/":
                res = "docstring/path mention only (`work/memory-stack/extract`, gitignored scratch) — reword"
            else:
                res = "command-string pointer — becomes a historical pointer to the new repo"
            w(f"| `{t}` | {', '.join('`'+c+'`' for c in callers[:4])}{' …' if len(callers)>4 else ''} ({len(callers)}) | {res} |")
    else:
        w("None.")
    w("")
    w("### 4a-ptr. Staying config/provenance strings naming moving paths (NOT blocking)")
    w("")
    w("Historical pointers. At 4D each becomes a one-line rewrite: the path points at the other repo.")
    w("")
    for f, l in pointer_hits[:40]:
        w(f"- `{f}` -> `{l}`")
    if len(pointer_hits) > 40:
        w(f"- … and {len(pointer_hits)-40} more")
    w("")
    w("### 4b. Legacy harnesses (EXP-001..023 evidence) naming moving code")
    w("")
    w("Non-blocking: these are frozen evidence, not live code. Their commands become historical pointers.")
    w("")
    if legacy_code_deps:
        for f, l in legacy_code_deps[:60]:
            w(f"- `{f}` -> `{l}`")
        if len(legacy_code_deps) > 60:
            w(f"- … and {len(legacy_code_deps)-60} more")
    else:
        w("None.")
    w("")
    w("### 4c. Moving python that imports staying modules")
    w("")
    w("These become cross-repo dependencies (vendor the shared module or install it).")
    w("")
    if py_reverse:
        for f, t in py_reverse:
            w(f"- `{f}` imports `{t}`")
    else:
        w("None.")
    w("")
    w("## 5. Verdict")
    w("")
    if blocking_files:
        w(f"**NO-GO as drawn: {len(blocking_files)} staying file(s) name moving code (4a).** Resolve each by one of: (1) keep that file in the ledger (move it off the MOVE list), (2) extract the shared piece into a small package both repos import, (3) rewrite the call to a pinned path in the other repo.")
    else:
        w("**GO** on the code side: no staying code depends on moving code.")
    w("")
    shared = sorted(t for t, cs in by_target.items()
                    if any(c.startswith(("bench/", "tools/")) for c in cs)
                    and (t.startswith(("tools/granite-runner", "bench/", "import bench/"))))
    if shared:
        w("Reclassification candidates (live hardware-lane callers; derived, not opinion): "
          + ", ".join(f"`{t.replace('import ', '')}`" for t in shared)
          + ". Moving them requires a shared package or leaving them in the ledger; the rest of the move set has no live callers.")
        w("")
    w("Always required, either way: spine corrections as new records, a `project` facet on ledger rows (done in P2), a registry rule for cross-repo instrument ids, and the EXP-038 retake finished before any file moves (its watchdog writes into `results/`).")
    w("")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(L) + "\n")
    print(f"wrote {out_path} — move {len(moving)}/{len(files)} files, {len(moving_instr)} instruments, "
          f"{total_refs} refs, {len(blocking_files)} blocking files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
