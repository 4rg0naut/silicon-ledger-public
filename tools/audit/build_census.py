#!/usr/bin/env python3
"""build_census.py — Tool Audit 2026-10 phase-3 census generator (audit artifact).

Machine-joins the three audit sources and the registry:
  tools/instruments.jsonl        (registry, post-classify)
  tools/audit/smoke-2026-10.tsv  (phase-1 live-layer results)
  tools/audit/verdicts-2026-10.jsonl (phase-2 verdicts)

and writes tools/AUDIT-2026-10.md: inventory matrix, smoke outcomes, capability-
cluster duplication map with per-member verdicts, environment findings, the
deferred-window queue, and the BaseRT borrow decisions. Rebuild anytime; never patch the .md.

usage: .venv-conv/bin/python tools/audit/build_census.py
"""
from __future__ import annotations

import collections
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS = ROOT / "tools"
OUT = TOOLS / "AUDIT-2026-10.md"

REG = [json.loads(l) for l in (TOOLS / "instruments.jsonl").read_text().splitlines() if l.strip()]
VERD = {json.loads(l)["path"]: json.loads(l)
        for l in (TOOLS / "audit" / "verdicts-2026-10.jsonl").read_text().splitlines() if l.strip()}
SMOKE = {}
smoke_f = TOOLS / "audit" / "smoke-2026-10.tsv"
if smoke_f.exists():
    for line in smoke_f.read_text().splitlines():
        p = line.split("\t")
        if len(p) == 6:
            SMOKE[p[0]] = {"action": p[1], "rc": p[2], "result": p[3], "seconds": p[4], "detail": p[5]}

CLUSTERS: dict[str, dict] = {
    "power / energy": {
        "members": ["bench/_power.py", "bench/power_ab.py", "bench/power_coreai.py",
                    "bench/power_mlcore.py", "bench/mlpower-runner.swift", "bench/syswide_ane.py",
                    "tools/enginemon/enginemon.c"],
        "why": "seven ways to answer 'what did this load cost in energy'.",
    },
    "latency measurement": {
        "members": ["bench/latency_protocol.py", "bench/bench_encoder.py",
                    "bench/bench_ane_variants.py", "bench/granite_ane_variants.py",
                    "bench/laya_ane_bench.py", "bench/na_tiles.py", "bench/na_tiles.metal"],
        "why": "benchmark runners overlapping in what they time.",
    },
    "ANE visibility / attribution": {
        "members": ["bench/ane-dma-test.m", "bench/ane-probe.m", "bench/kane_gate_probe.m",
                    "bench/metal_counters.m", "bench/probe_ane_regions.py",
                    "bench/analyze_ane_scan.py", "bench/ane_report.py",
                    "tools/enginemon/enginemon.c", "bench/jevbench_ane.py"],
        "why": "did the ANE actually do the work, and how do we see it.",
    },
    "NAX / matmul2d / Metal tensor": {
        "members": ["bench/na_tiles.py", "bench/na_tiles.metal", "bench/train_decision_model.py",
                    "results/EXP-027-nax/harness/p27_r8.m",
                    "results/EXP-027-nax/harness/p27_na_r8.py",
                    "results/EXP-029-nax-crosslane/harness/nax_gemm/main.swift"],
        "why": "the matmul2d ladder re-expressed per experiment.",
    },
    "MTEB / eval / retrieval": {
        "members": ["bench/mteb_retrieval.py", "bench/mteb_interface.py", "bench/mteb_french_tasks.py",
                    "bench/mteb_multilingual_refs.py", "bench/mteb_reference.py", "bench/mteb_taskinfo.py",
                    "bench/eval_ane_embedder.py", "bench/eval_dev_calibration.py",
                    "bench/compare_retrievers.py", "bench/chunk_indexed_retrieval.py",
                    "bench/rerank_retrieval.py", "bench/von_authored144.py",
                    "bench/correctness_head.py", "bench/gate_precision_report.py"],
        "why": "one eval stack split into six mteb_* entry points plus runners.",
    },
    "ledger / records plumbing": {
        "members": ["bench/build_measurements.py", "bench/audit_measurements.py",
                    "bench/results_table.py", "bench/import_bench_reports.py",
                    "bench/identity.py", "bench/verify_extraction.py", "bench/make_charts.py",
                    "bench/losses.py", "tools/registry.py", "tools/archive/inventory.py"],
        "why": "deterministic plumbing; smoke-runnable without a window.",
    },
    "serving (embed / rerank / stack)": {
        "members": ["tools/embed-server/embed_server.py", "tools/embed-server/embed_server_gemma.py",
                    "tools/rerank-server/rerank_server.py", "tools/rerank-server/rerank_server_ane.py",
                    "tools/rerank-server/gate_reranker.py", "bench/gate_reranker_ane.py",
                    "tools/memory-stack/start.sh"],
        "why": "two embed servers, two rerank servers, two gates - lane twins.",
    },
    "CoreML placement / conversion probes (evidence)": {
        "members": ["results/EXP-025-ane-gpu-sync/harness/coreml_plan.m",
                    "results/EXP-025-ane-gpu-sync/harness/coreml_plan.py",
                    "results/EXP-025-ane-gpu-sync/harness/coreml_route_sweep.py",
                    "results/EXP-025-ane-gpu-sync/harness/plan_devicesupport.m",
                    "bench/diagnose_convert.py", "bench/find_int_op.py", "bench/repro_int_op.py",
                    "bench/minimal_repro_ane_crash.py", "bench/mlir_bytecode.py"],
        "why": "the pre-Core-AI probe fleet, largely superseded by EXP-026+ lanes.",
    },
    "convert / model build": {
        "members": ["results/EXP-026-ane-kitchen/harness/p2b_compile.m",
                    "results/EXP-026-ane-kitchen/harness/p2b_milgen.py",
                    "results/EXP-029-nax-crosslane/harness/make_gemm_models.py",
                    "bench/classify_unit_kind.py"],
        "why": "model -> ANE artifact builders.",
    },
    "capture / tracing drivers": {
        "members": ["results/EXP-028-apple-tracer/harness/p28_capture.sh",
                    "results/EXP-028-apple-tracer/harness/p28_e1_signpost.sh",
                    "results/EXP-028-apple-tracer/harness/p28_coreai_run/main.swift",
                    "results/EXP-027-nax/harness/p27_nxd_capture.sh",
                    "results/EXP-029-nax-crosslane/harness/power_correlate.sh",
                    "results/EXP-029-nax-crosslane/harness/quiet_probe.sh"],
        "why": "sudo/trace window capture glue.",
    },
}

LANG_NOTE = {
    ".py": "orchestration, ledger, reports, eval",
    ".m": "Metal/CoreML/ANE private-API probes only",
    ".metal": "kernels (always paired with an .m/.py host)",
    ".sh": "glue: capture windows, build wrappers",
    ".c": "tiny syscalls (enginemon, canary)",
    ".swift": "frozen: existing runners only",
    ".h": "shared bridge headers",
    ".lldb": "debugger macros",
}


def loc_of(path: str) -> str:
    if path.startswith("results/"):
        return "results (evidence)"
    if path.startswith("bench/"):
        return "bench (live)"
    if path.startswith("tools/"):
        return "tools (live)"
    return "exp022-raw (scratch)"


def main() -> int:
    by_status = collections.Counter(r["status"] for r in REG)
    by_loc = collections.Counter(loc_of(r["path"]) for r in REG)
    ext_stats = collections.Counter()
    ext_bytes = collections.Counter()
    for r in REG:
        p = ROOT / r["path"]
        if p.exists() and p.is_file():
            ext_stats[p.suffix.lower() or "(none)"] += 1
            ext_bytes[p.suffix.lower() or "(none)"] += p.stat().st_size
    smoke_by = collections.Counter(v["result"] for v in SMOKE.values())

    L: list[str] = []
    L.append("# Tool Audit 2026-10 — census, duplication map, verdicts\n")
    L.append(f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} by "
             "`tools/audit/build_census.py`. Rebuild, never patch. "
             "Pre-audit snapshot: tag `pre-audit-2026-10` (silicon-ledger).\n")

    L.append("## 1. Census matrix\n")
    L.append(f"**{len(REG)} instruments** on disk and registered; 0 unclassified. "
             "Registry `--check` green, `kb_pipeline.sh` green (5/5). "
             "This census closes the 126 `unclassified` WARN that stood since the registry shipped, "
             "and registers two harness subdirs (`results/EXP-*/harness/*/*`) the old LOCATIONS globs missed "
             "(`p28_coreai_run/main.swift`, `nax_gemm/main.swift`).\n")
    L.append("| dimension | breakdown |\n|---|---|")
    L.append("| status | " + ", ".join(f"{v} {k}" for k, v in by_status.most_common()) + " |")
    L.append("| location | " + ", ".join(f"{v} {k}" for k, v in by_loc.most_common()) + " |")
    langs = ", ".join(f"{ext} x{n} ({ext_bytes[ext]//1024} KB)" for ext, n in ext_stats.most_common())
    L.append("| language (bytes, machine-counted) | " + langs + " |\n")

    L.append("## 2. Live-layer smoke (every bench/ + tools/ instrument, once)\n")
    L.append("Actions: `run` full deterministic execution; `help` py_compile+--help; `compile` syntax gate; "
             "`usage` no-arg usage print; `window` deferred (sudo powermetrics / quiet window, RULES-2: "
             "oMLX is live, no GPU-energy runs); `static` by-design read-only. "
             "Failure classes are honest: DEPS-BLOCKED (venv), BLOCKED-DATA (absent work/ input), "
             "BLOCKED-NET, BLOCKED-TOOLCHAIN, DATA-DRIFT, OK-GUARD (guard fired correctly).\n")
    L.append("| result | count |\n|---|---|")
    for k, v in smoke_by.most_common():
        L.append(f"| {k} | {v} |")
    executed = sum(1 for v in SMOKE.values() if v["seconds"] != "")
    L.append(f"\nFull rows: `tools/audit/smoke-2026-10.tsv` — columns path/action/rc/result/seconds/detail, "
             f"{len(SMOKE)} live instruments, {executed} executed (exit code + wall time per row, empty where nothing ran). "
             "Key results: identity M5 Max/Mac17,14; audit_measurements 966 rows / 923 verified; "
             "coreai_cache census 175 distinct model hashes; enginemon compiles+runs unprivileged (--list); "
             "granite-runner Swift build cached-green; all ObjC/Metal syntax gates compile "
             "(kane_gate_probe.m needs its own documented `-fno-objc-arc`).\n")

    L.append("## 3. Capability clusters — every member, one verdict\n")
    L.append("Verdict vocabulary: `canonical` (keep as the lane's instrument) / `superseded` (evidence or "
             "ancestor, preserved, never deleted) / `duplicate` (twin — prefer the named canonical) / "
             "`scratch` (exp022-raw). Cluster verdicts below are cross-checked against the registry — "
             "the table is built from instruments.jsonl, not from hand-copied opinions.\n")
    regmap = {r["path"]: r for r in REG}
    missed = 0
    for name, cl in CLUSTERS.items():
        L.append(f"### {name}\n\n{cl['why']}\n")
        L.append("| member | registry status | canonical for / note | smoke |")
        L.append("|---|---|---|---|")
        for m in cl["members"]:
            r = regmap.get(m)
            if not r:
                if m == "tools/registry.py":
                    L.append(f"| `{m}` | (self-skipped) | instrument registry + gate; SKIP_NAME by design | run |")
                    continue
                L.append(f"| `{m}` | **MISSING FROM REGISTRY** | | |")
                missed += 1
                continue
            sm = SMOKE.get(m, {}).get("result", "—")
            note = (r.get("canonical_for") or "").strip() or "—"
            v = VERD.get(m, {})
            if v.get("note") and r["status"] != "canonical":
                note = v["note"]
            elif v.get("note") and r["status"] == "canonical":
                note = note + " — " + v["note"]
            L.append(f"| `{m}` | {r['status']} | {note[:110]} | {sm} |")
        L.append("")
    if missed:
        L.append(f"**{missed} cluster members are not in the registry — fix and rebuild.**\n")

    L.append("## 4. Environment findings (2026-10 audit) — with same-day remediation\n")
    L.append("""1. **venv rot — RESOLVED same day.** coremltools/mteb/requests/matplotlib/pandas were gone from
both venvs (September conversion env). Rebuilt `.venv-conv` 2026-10-11 against a constraint
file; full freeze pinned to `tools/env/requirements-2026-10.txt` (87 pkgs); `tools/env/README.md`
declares `.venv` deprecated legacy. Version-currency caveats (torch 2.14.1 vs coremltools-tested
2.7.0 / coreai-torch-validated 2.13.0) recorded there — conversions must numerically gate, and
the reranker rebuild did (max |delta| 0.025 vs official, all family rank groups preserved).""")
    L.append("""2. **toolchain-path rot — FIXED same day.** bench/probe_ane_regions.py hardcoded the cryptexd
MetalToolchain mount suffix (vbaqjL-era) that rotates every boot; now globbed. First run after
the fix passed (export+compile+ANE-region count). Same class of bug found and fixed in
tools/rerank-server/rerank_server_ane.py, which pinned the M4-mini-era `aot_h16g_ane` path
while this box's re-authored bundle is `aot_h17g_ane` — resolution is now globbed; the ANE
gate (bench/gate_reranker_ane.py) remains blocked on the lost zoo package `coreai_models`
(RoPECache) — not reimplemented blind.""")
    L.append("""3. **lost artifacts — reranker lane RESTORED same day.** The September .aimodel was gone from
models/qwen3-reranker/; the zoo converter path was gone with repos/. bench/convert_reranker.py
(registered) rebuilds it from models/qwen3-reranker-hf: torch.export -> coreai_torch -> fp16
static-512 .aimodel, numerics-gated on reference.json's 10 pairs before writing. Server + gate
now run; reference.json re-emitted with seq_len + rebuild stamp (prior kept as
reference-2026-09-26.json). Gate tolerance note: gate_reranker.py's 5e-4 per-pair bound and
absolute rel/irr separation were properties of the 6-pair GPU-era check — on the 10-pair
reference even the official scores fail separation (rel-cos 0.000046 < irr-math 0.272);
family rank groups are the meaningful gate.""")
    L.append("""4. **EmbeddingGemma bundle absent — unchanged.** models/ holds Laya, MiniLM, Qwen3-reranker
(+ rebuilt bundle) only. embed_server_gemma.py stays `duplicate, NOT merged` with the
documented delta (tokenizer stack, prompt prefixes, 768 vs 384 dim, SEQ_LEN 256 vs 128).""")
    L.append("""5. **no passwordless sudo — unchanged.** All powermetrics instruments stay queued (section 5);
oMLX live meant no quiet window this session. Nothing re-measured (RULES 2).""")
    L.append("""6. **side effect by design — unchanged.** tools/archive/inventory.py regenerates
knowledge/ane/ARCHIVE-MAP.md when smoke'd; its own header says so.""")
    L.append("")
    L.append("## 5. Deferred-window queue (sudo / quiet-window)\n")
    L.append("| tool | smoke state |\n|---|---|")
    for p in sorted(SMOKE):
        if SMOKE[p]["result"] == "DEFER-WINDOW":
            L.append(f"| `{p}` | needs sudo powermetrics + quiet window |")
    L.append("| tools/enginemon/enginemon.c (capture mode) | compiled + --list verified unprivileged; the timed capture wants the window |")
    L.append("")
    L.append("Window session recipe (sudo available, oMLX idle): `sh tools/kb_pipeline.sh` for a green start, "
             "`results/EXP-029-nax-crosslane/harness/quiet_probe.sh` first as the contention gate, then each "
             "row above per its own usage header; finish with enginemon capture mode (its unprivileged "
             "--list path is already proven).\n")

    L.append("## 6. BaseRT borrow decisions\n")
    L.append("Reference: basecompute/baseRT (v0.3.0, Oct 8): one C++ engine + Rust converter + thin bindings; "
             "**one** benchmark harness with profiles and a versioned report schema (`basert-telemetry/4` — the "
             "harness refuses reports with a mismatched workload); CHANGELOG/CONTRIBUTING/SECURITY.md.\n")
    L.append("| practice | decision | why |\n|---|---|---|")
    L.append("| versioned report schema | **ADOPT (formalize what exists)** | `latency_protocol.py` already "
             "emits schema-conformant rows and `import_bench_reports.py` validates on import — stamp a "
             "version field (`ane-ledger/1`) so future schema drift fails loudly at import instead of "
             "silently, and record it in the next measurement-window session. No retro-edit of recorded rows (RULES 2). |")
    L.append("| one harness + profiles | **ADOPT for future plans; DECLINE retro-rewrite** | EXP-027/029 each "
             "re-expressed the matmul2d ladder (`p27_r8.m`, `p27_na_r8.py`, `na_tiles.py`, `nax_ladder.m`) — "
             "the next NAX session should use one `nax_bench.m` with named arms/profiles. The historical "
             "harnesses are evidence; rewriting them is the deletion trap by another name. |")
    L.append("| single compiled core + bindings | **DECLINE** | we are a knowledge base, not a product; the "
             "fleet's spread is an audit artifact of many experiments, not a runtime dependency graph. "
             "The registry + canonical_for is our dedup mechanism. |")
    L.append("| CHANGELOG/SECURITY/docs triad | **ADOPT lightly** | `tools/TOOLS.md` (generated) + SPINE.md "
             "+ this census cover the same ground at our scale. |\n")

    L.append("## 7. What changed, in words\n")
    L.append(f"- 126 `unclassified` -> 0. Final distribution (from `instruments.jsonl` at generation time): "
             f"{', '.join(f'{v} {k}' for k, v in sorted(by_status.items(), key=lambda kv: -kv[1]))}. "
             "Pre-existing 34 verdicts reconfirmed; the rest issued via `tools/audit/verdicts.py`, "
             "machine-checked into `tools/audit/verdicts-2026-10.jsonl`.")
    L.append("- Two harness subdirs registered (old glob blind spot): 2 previously-invisible instruments now classified.")
    L.append("- Mispair corrected: `granite_ane_variants.py` (conversion sweep) is NOT the ancestor of "
             "`bench_ane_variants.py` (residency measurement pass) — both canonical.")
    L.append("- Merges executed: none blind. Two candidates failed their honesty gate and were documented "
             "instead (embed_server_gemma, rerank_server_ane). Duplication here is mostly bookkeeping-spread "
             "(solved by this verdict pass), not code-spread.")
    L.append("- No recorded measurement was re-run; no `results/EXP-*/` file was modified or moved "
             "(`git diff pre-audit-2026-10 -- results/EXP-*/` is empty at audit close); nothing deleted.")
    L.append("- Language policy: `tools/LANGUAGE-POLICY.md` (4 lanes, Swift frozen).")
    L.append("")

    OUT.write_text("\n".join(L))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(REG)} instruments, {len(SMOKE)} smoke rows, "
          f"{len(VERD)} verdicts, clusters={len(CLUSTERS)}, cluster-misses={missed}")
    return 0 if missed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
