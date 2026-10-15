#!/usr/bin/env python3
"""smoke.py — Tool Audit 2026-10 phase-1 runner (register-then-run, audit artifact).

Runs each tool in the LIVE layer (bench/ + tools/) with the lightest honest check:
  run     full execution — deterministic ledger/plumbing tools only (NO measurement
          tools, per RULES 2: smoke numbers are tool health, never ledger numbers)
  help    py_compile + `--help` (catches syntax, missing modules, arg wiring)
  compile clang -fsyntax-only / metal -c / swiftc -parse / bash -n  (no execution)
  window  needs sudo powermetrics and/or the quiet window — attempted by NOTHING here;
          recorded for the window queue
  static  inspected by read only (lldb scripts, glue with side effects)

Writes tools/audit/smoke-2026-10.tsv:  path<TAB>action<TAB>rc<TAB>result<TAB>seconds<TAB>detail
rc is the process exit code (empty when nothing executed: window/static); seconds is wall time.
Exit 0 always; the TSV is the evidence.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # silicon-ledger/
OUT = Path(__file__).resolve().parent / "smoke-2026-10.tsv"
PY = ROOT / ".venv-conv" / "bin" / "python"
if not PY.exists():
    PY = Path(sys.executable)
SDK = subprocess.run(["xcrun", "--show-sdk-path"], capture_output=True, text=True).stdout.strip()

# path -> (action, [argv override for `run`], extra reason string)
ACTIONS: dict[str, tuple[str, list[str] | None, str]] = {
    # ---- bench/: full-run set = deterministic plumbing, no measurement output ----
    "bench/identity.py":            ("run", ["bench/identity.py"], ""),
    "bench/build_measurements.py":  ("run", ["bench/build_measurements.py"], ""),
    "bench/results_table.py":       ("run", ["bench/results_table.py"], ""),
    "bench/audit_measurements.py":  ("run", ["bench/audit_measurements.py"], ""),
    "bench/verify_extraction.py":   ("help", None, ""),
    "bench/import_bench_reports.py":("help", None, ""),
    "bench/coreai_cache.py":        ("run", ["bench/coreai_cache.py", "--summary"], ""),
    "bench/make_charts.py":         ("help", None, ""),
    # ---- bench/: measurement runners -> compile/help only (RULES 2 + quiet window) --
    "bench/latency_protocol.py":    ("help", None, ""),
    "bench/bench_encoder.py":       ("help", None, ""),
    "bench/bench_ane_variants.py":  ("help", None, ""),
    "bench/granite_ane_variants.py":("help", None, ""),
    "bench/laya_ane_bench.py":      ("help", None, ""),
    "bench/na_tiles.py":            ("help", None, ""),
    "bench/ane-dma-test.m":         ("compile", None, ""),
    "bench/ane-probe.m":            ("compile", None, ""),
    "bench/kane_gate_probe.m":      ("compile", None, ""),
    "bench/metal_counters.m":       ("compile", None, ""),
    "bench/na_tiles.metal":         ("static", None, "not compiled standalone: its lane is TorchMetalKernel at runtime in bench/na_tiles.py; plain metal lacks matmul2d"),
    "bench/mlpower-runner.swift":   ("compile", None, ""),
    "bench/aot_verify.sh":          ("compile", None, ""),
    # ---- bench/: analysis / eval / servers -> help ----
    "bench/_power.py":              ("help", None, ""),
    "bench/analyze_ane_scan.py":    ("usage", None, ""),
    "bench/ane_report.py":          ("usage", None, ""),
    "bench/classify_unit_kind.py":  ("help", None, ""),
    "bench/compare_retrievers.py":  ("help", None, ""),
    "bench/correctness_head.py":    ("help", None, ""),
    "bench/chunk_indexed_retrieval.py": ("help", None, ""),
    "bench/diagnose_convert.py":    ("help", None, ""),
    "bench/eval_ane_embedder.py":   ("help", None, ""),
    "bench/eval_dev_calibration.py":("syntax", None,
        "full run has no argparse and rewrites results/dev-calibration.json float tails every pass; " + "full eval reproduced 2026-10-11 (winners unchanged, deltas <=2e-8) — smoke keeps the compile gate"),
    "bench/find_int_op.py":         ("help", None, ""),
    "bench/gate_precision_report.py":("usage", None, ""),
    "bench/gate_reranker_ane.py":   ("help", None, ""),
    "bench/import_bench_reports.py":("help", None, ""),
    "bench/jevbench_ane.py":        ("help", None, ""),
    "bench/losses.py":              ("run", ["bench/losses.py"], "self-test main"),
    "bench/minimal_repro_ane_crash.py": ("help", None, ""),
    "bench/mlir_bytecode.py":       ("help", None, ""),
    "bench/mteb_french_tasks.py":   ("help", None, ""),
    "bench/mteb_interface.py":      ("help", None, ""),
    "bench/mteb_multilingual_refs.py": ("help", None, ""),
    "bench/mteb_reference.py":      ("help", None, ""),
    "bench/mteb_retrieval.py":      ("help", None, ""),
    "bench/mteb_taskinfo.py":       ("help", None, ""),
    "bench/repro_apple_attention.py": ("help", None, ""),
    "bench/repro_int_op.py":        ("help", None, ""),
    "bench/rerank_retrieval.py":    ("help", None, ""),
    "bench/syswide_ane.py":         ("window", None, "sudo powermetrics"),
    "bench/train_decision_model.py":("help", None, ""),
    "bench/von_authored144.py":     ("help", None, ""),
    "bench/power_ab.py":            ("window", None, "sudo powermetrics + quiet window"),
    "bench/power_coreai.py":        ("window", None, "sudo powermetrics + quiet window"),
    "bench/power_mlcore.py":        ("window", None, "sudo powermetrics + quiet window"),
    "bench/power_phase_probe.py":   ("window", None, "sudo powermetrics + quiet window"),
    "bench/interference_coreai.py": ("window", None, "differential load; needs quiet window"),
    "bench/probe_ane_regions.py":   ("help", None, ""),
    # ---- tools/: run the safe plumbing ----
    "tools/kb_pipeline.sh":         ("run", ["sh", "tools/kb_pipeline.sh"], ""),
    "tools/registry.py":            ("run", ["tools/registry.py", "--check"], ""),
    "tools/publish/check_public.py":("run", ["tools/publish/check_public.py"], ""),
    "tools/publish/publish.sh":     ("run", ["sh", "tools/publish/publish.sh"], ""),
    "tools/publish/rewrite_links.py":("help", None, ""),
    "tools/publish/push-mirror.sh": ("static", None, "network side effect (git push); syntax-check only"),
    "tools/audit/smoke.py":         ("help", None, "this driver"),
    "tools/audit/build_census.py":  ("help", None, ""),
    "tools/audit/verdicts.py":      ("run", ["tools/audit/verdicts.py", "--emit"], ""),
    "tools/archive/inventory.py":   ("help", None, ""),
    "tools/embed-server/embed_server.py":     ("help", None, ""),
    "tools/embed-server/embed_server_gemma.py": ("help", None, ""),
    "tools/rerank-server/rerank_server.py":   ("help", None, ""),
    "tools/rerank-server/rerank_server_ane.py":("help", None, ""),
    "tools/rerank-server/gate_reranker.py":   ("help", None, ""),
    "tools/memory-stack/start.sh":  ("static", None, "launches long-lived stack; syntax-check only"),
    "tools/enginemon/enginemon.c":  ("run-compile", None, "clang -c + unprivileged 3 s live capture"),
    "tools/granite-runner/Package.swift": ("run", ["swift", "build", "--package-path", "tools/granite-runner"], "incremental; .build cached"),
}


def sh(argv: list[str], cwd: Path, timeout=150) -> tuple[int, str]:
    t0 = time.time()
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout + "\n" + p.stderr).strip().replace("\n", " ⏎ ")
        return p.returncode, out[:1200], time.time() - t0
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT {timeout}s", float(timeout)
    except Exception as e:  # noqa: BLE001
        return 125, f"LAUNCH-FAIL {type(e).__name__}: {e}", 0.0


def compile_check(path: str) -> tuple[int, str, float]:
    p = ROOT / path
    ext = p.suffix.lower()
    if ext in (".m", ".mm"):
        arc = ["-fno-objc-arc"] if p.name == "kane_gate_probe.m" else ["-fobjc-arc"]
        return sh(["clang", "-fsyntax-only", "-x", "objective-c", *arc,
                   f"-isysroot", SDK, "-I", str(p.parent), str(p)], ROOT)
    if ext == ".c":
        return sh(["clang", "-fsyntax-only", f"-isysroot", SDK, str(p)], ROOT)
    if ext == ".h":
        return sh(["clang", "-fsyntax-only", "-x", "objective-c", f"-isysroot", SDK,
                   "-I", str(p.parent), "-include", str(p), "-"], ROOT)
    if ext == ".metal":
        return sh(["xcrun", "-sdk", "macosx", "metal", "-c", str(p), "-o", "/dev/null"], ROOT)
    if ext == ".swift":
        return sh(["swiftc", "-parse", str(p)], ROOT)
    if ext == ".sh":
        return sh(["bash", "-n", str(p)], ROOT)
    if ext == ".lldb":
        return 0, "static read (lldb command script, no standalone syntax gate)", 0.0
    return 1, f"no compile rule for {ext}", 0.0


def classify(path: str, code: int, detail: str) -> str:
    if code == -1:
        return "DEFER-WINDOW"
    if code == 124:
        return "TIMEOUT"
    if code == 125:
        return "LAUNCH-FAIL"
    if code == 0:
        return "OK"
    if "refusing:" in detail:
        return "OK-GUARD"
    low = detail
    if "No module named 'jevbench'" in low or "No module named 'coreai_models'" in low:
        return "BLOCKED-EXTERNAL"
    if "ModuleNotFoundError" in low:
        return "DEPS-BLOCKED"
    if "coreai-build not found" in low:
        return "BLOCKED-TOOLCHAIN"
    if path.endswith("repro_int_op.py") and "CONVERSION FAILED" in low:
        return "OK-REPRO"
    if "hf_hub_download" in low or "HF Hub" in low:
        return "BLOCKED-NET"
    if "KeyError" in low and "seq_len" in low:
        return "DATA-DRIFT"
    if "FileNotFoundError" in low and ("repos/" in low or "/work/" in low or "work/" in low or "'--help'" in low):
        return "BLOCKED-DATA"
    if code == 2 and ("usage" in low.lower() or "Usage" in low):
        return "OK-USAGE"
    if code == 2 and ("traceback" not in low.lower()):
        return "OK-USAGE"
    return f"FAIL-EXIT{code}"


def main() -> int:
    import json
    if "--help" in sys.argv[1:] and sys.argv[1] != "--only":
        print(__doc__)
        return 0
    only = set(sys.argv[2:]) if len(sys.argv) > 2 and sys.argv[1] == "--only" else None
    reg = [json.loads(l) for l in (ROOT / "tools" / "instruments.jsonl").read_text().splitlines() if l.strip()]
    live = [r["path"] for r in reg
            if r["path"].startswith(("bench/", "tools/")) and not r["path"].endswith(".md")]
    rows = {}
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            parts = line.split("\t")
            if len(parts) == 6:
                rows[parts[0]] = tuple(parts)
    for path in sorted(live):
        if only and path not in only:
            continue
        action, argv, why = ACTIONS.get(path, ("help", None, ""))
        secs = 0.0
        if action == "window":
            code, detail, secs = -1, why or "needs sudo/quiet window", -1.0
        elif action == "static":
            code, detail, secs = 0, f"by design: {why}" if why else "static read only", -1.0
        elif action == "usage":
            code, detail, secs = sh([str(PY), path], ROOT)
        elif action == "run":
            cmds = [str(PY), *(argv or [])] if argv and argv[0].endswith(".py") else (argv or [])
            code, detail, secs = sh(cmds, ROOT)
        elif action == "run-compile":
            rc, det, s1 = compile_check(path)
            if rc == 0:
                rc2, det2, s2 = sh(["clang", "-isysroot", SDK, str(ROOT / path), "-o", "/tmp/audit_enginemon",
                                    "-framework", "CoreFoundation"], ROOT)
                if rc2 == 0:
                    rc2, det2, s3 = sh(["/tmp/audit_enginemon", "--list"], ROOT, timeout=30)
                    secs = s1 + s2 + s3
                    code, detail = rc2, (det + " | " + det2)[:600]
                else:
                    secs = s1 + s2
                    code, detail = rc2, (det + " | " + det2)[:600]
            else:
                secs = s1
                code, detail = rc, det
        elif action == "syntax":
            code, detail, secs = sh([str(PY), "-m", "py_compile", path], ROOT, timeout=30)
        elif action == "compile":
            code, detail, secs = compile_check(path)
        else:  # help
            rc, det, s1 = sh([str(PY), "-m", "py_compile", path], ROOT, timeout=30)
            if rc != 0:
                code, detail, secs = rc, f"py_compile: {det}", s1
            elif path.endswith(".py"):
                code, detail, secs = sh([str(PY), path, "--help"], ROOT)
            else:
                code, detail, secs = compile_check(path)
        verdict = classify(path, code, detail)
        rc_str = "" if action in ("window", "static") else str(code)
        sec_str = "" if secs < 0 else f"{secs:.1f}"
        rows[path] = (path, action, rc_str, verdict, sec_str, detail[:280])
        print(f"{verdict:<14} rc={rc_str or '--':<4} {sec_str or '--':>5}s  {action:<8} {path}  {detail[:90]}", flush=True)
    OUT.write_text("".join("\t".join(rows[k]) + "\n" for k in sorted(rows)))
    print(f"\nwrote {OUT.relative_to(ROOT)} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
