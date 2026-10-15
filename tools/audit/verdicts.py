#!/usr/bin/env python3
"""verdicts.py — Tool Audit 2026-10 phase-2/3 verdict engine.

One map, every previously-unclassified instrument, one verdict each:
  canonical   = the front door for its capability (name kept; convention noted)
  duplicate   = exists, prefer its canonical twin (file stays, behavior frozen)
  superseded  = evidence artifact / answered probe / merged ancestor — never deleted
  scratch     = one-shot wrapper, kept where it lives

`--emit` writes tools/audit/verdicts-2026-10.jsonl (the registry's data source);
`--check` reports registry entries with no verdict so nothing silently stays TODO.
Owner directive (session 2026-10-11): consolidate, do not spread; experiment
evidence under results/ is judged, never rewritten.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
JSONL = HERE / "verdicts-2026-10.jsonl"

E = "EXP README records the result; this file is preserved evidence, not an instrument."

V: dict[str, tuple[str, str, str]] = {
    # ================= bench/ — reusable instruments (canonical) =================
    "bench/analyze_ane_scan.py":   ("canonical", "ane-probe scan analysis (CSV)", "Live analyzer; input CSVs are produced on the M4 fleet by bench/ane-probe.m — local runs need a scan drop (BLOCKED-DATA here is fleet-data absence, not tool damage). Pair: bench/ane-probe.m."),
    "bench/ane_report.py":         ("canonical", "xctrace ANE hardware-interval summary", "Reusable with any .trace on this machine — not an evidence-only file."),
    "bench/ane-probe.m":           ("canonical", "ANE API surface scan (per-machine)", "Upstream-PR carrier (README); M4 + M5 Max rows exist."),
    "bench/ane-dma-test.m":        ("canonical", "M4 kernel-DMA notch probe (fleet: M4 mini)", "Answer for M5 Max in EXP-020; re-runnable on the M4 mini per FLEET."),
    "bench/kane_gate_probe.m":     ("canonical", "per-task kANE_* counter gate probe", ""),
    "bench/metal_counters.m":      ("canonical", "MTLDevice counter-sampling fallback ladder", ""),
    "bench/aot_verify.sh":         ("canonical", "AOT compile + bundle load verify", ""),
    "bench/bench_ane_variants.py": ("canonical", "ANE residency measurement pass (variant x CU, enginemon + granite-runner)", "Living measurement pass; not an ancestor of granite_ane_variants.py — that tool sweeps conversions. 2026-10 audit: pair long mis-paired in verdict drafts."),
    "bench/bench_encoder.py":      ("canonical", "Core ML encoder unit-placement bench", "Timing inside should adopt latency_protocol conventions on next run."),
    "bench/compare_retrievers.py": ("canonical", "retriever A/B (same reranker)", ""),
    "bench/correctness_head.py":   ("canonical", "correctness head (two-channel fix)", "EXP-019 feature scorer."),
    "bench/classify_unit_kind.py": ("canonical", "unit-kind classifier on ANE (Laya)", ""),
    "bench/coreai_cache.py":       ("canonical", "Core AI specialization-cache decoder (read-only)", ""),
    "bench/diagnose_convert.py":   ("canonical", "coremltools conversion failure diagnosis", ""),
    "bench/eval_ane_embedder.py":  ("canonical", "HTTP embedder scoring on zoo multilingual tasks", ""),
    "bench/eval_dev_calibration.py":("canonical", "dev-split calibration evaluation", ""),
    "bench/gate_precision_report.py":("canonical", "full numerical + retrieval gate", ""),
    "bench/gate_reranker_ane.py":  ("canonical", "reranker gate — ANE AOT delegate", "JIT twin: tools/rerank-server/gate_reranker.py."),
    "bench/identity.py":           ("canonical", "machine identity (chip/hw_model/cores/arch/os/os_build)", ""),
    "bench/import_bench_reports.py":("canonical", "silicon-ledger-bench claims merge", ""),
    "bench/jevbench_ane.py":       ("canonical", "JevBench adapters for ANE ports", ""),
    "bench/laya_ane_bench.py":     ("canonical", "Laya ANE fidelity + latency + residency", ""),
    "bench/losses.py":             ("canonical", "decision-model losses library", ""),
    "bench/make_charts.py":        ("canonical", "stack-status charts from measurements", ""),
    "bench/mlir_bytecode.py":      ("canonical", "MLIR bytecode reader (Core AI mpsgraph plans)", ""),
    "bench/mteb_retrieval.py":     ("canonical", "MTEB retrieval harness (ANE embed server)", "Five mteb_* probes superseded into this + the KB."),
    "bench/repro_int_op.py":       ("canonical", "coremltools int() minimal repro (PR asset)", ""),
    "bench/train_decision_model.py":("canonical", "decision-model trainer (ModernBERT + marker head)", ""),
    "bench/von_authored144.py":    ("canonical", "Von authored144 parity harness (HF vs ANE)", ""),
    "bench/smoke-audit-driver":    ("canonical", "", ""),  # placeholder removed at emit if unmatched
    # ================= bench/ — superseded (answered / ancestors) =================
    "bench/chunk_indexed_retrieval.py": ("superseded", "", E + " Pipeline reruns live in compare_retrievers.py."),
    "bench/granite_ane_variants.py": ("canonical", "Granite conversion-variant sweep (quant x seq x opset -> ANE partition outcome)", "EXP-005 instrument. NOT the ancestor of bench_ane_variants.py: diff 2026-10 shows ~272 differing lines, different mechanism (conversion sweep vs residency measurement). Both canonical, different jobs."),
    "bench/convert_reranker.py":   ("canonical", "reranker .aimodel rebuild route (HF -> torch.export -> coreai_torch, s512 fp16)", "Rebuilt 2026-10-11 after the September zoo converter was lost with repos/. Numerics-gated: rank_groups + max|delta|<=0.05 vs official before the bundle is written."),
    "bench/find_int_op.py":        ("superseded", "", "Pinpoint probe; op identified, repro lives in repro_int_op.py. " + E),
    "bench/minimal_repro_ane_crash.py": ("superseded", "", "Bisection record (NOT a reproduction, its own docstring says so); crash root cause = disk space, EXP-018. " + E),
    "bench/mteb_french_tasks.py":  ("superseded", "", "Exploratory probe; answer in EXP-008 + KB. " + E),
    "bench/mteb_interface.py":     ("superseded", "", "Introspection probe; wrapper now lives, see mteb_retrieval.py. " + E),
    "bench/mteb_multilingual_refs.py": ("superseded", "", "Reference-table scrape; numbers in EXP-015. " + E),
    "bench/mteb_reference.py":     ("superseded", "", "Reference run; superseded by mteb_retrieval.py. " + E),
    "bench/mteb_taskinfo.py":      ("superseded", "", "Task metadata scrape; superseded by mteb_retrieval.py. " + E),
    "bench/power_phase_probe.py":  ("superseded", "", "Burst/sustained discriminator — EXP-005 answered it. " + E),
    "bench/probe_ane_regions.py":  ("superseded", "", "dtype-decides-placement probe — EXP-005 answered it. " + E),
    "bench/repro_apple_attention.py": ("superseded", "", "Unblocked EXP-013; its lesson (hoist RoPE gather) is in the KB. " + E),
    "bench/rerank_retrieval.py":   ("superseded", "", E + " Rerank pipeline continues as rerank_server + gates."),
    "bench/syswide_ane.py":        ("duplicate", "superseded-by: bench/power_coreai.py + tools/enginemon/enginemon.c", "Prefer power_coreai.py (joules A/B) + tools/enginemon (lane activity)."),
    "bench/mlpower-runner.swift":  ("superseded", "", "Swift ancestor of power_mlcore.py (python, uses _power parser). Language consolidation 2026-10-11."),
    # ================= tools/ =================
    "tools/embed-server/embed_server.py": ("canonical", "OpenAI-shape /v1/embeddings server (parameterized: bundle/tokenizer/prompts)", ""),
    "tools/embed-server/embed_server_gemma.py": ("duplicate", "superseded-by: tools/embed-server/embed_server.py", "Variant twin of embed_server.py: HF tokenizers stack, prompt-prefix encoding, AOT recycle signature (MPSCommandBufferImageCache). NOT merged 2026-10-11 — bundle absent on this box, so merge equivalence is unprovable; canonical for everything else."),
    "tools/rerank-server/rerank_server.py": ("canonical", "rerank server — JIT GPU lane", "Runtime currently blocked: models/qwen3-reranker/*.aimodel absent from disk (only reference.json + tokenizer/ left); rebundle needs coremltools (missing from venvs). 2026-10 audit finding."),
    "tools/rerank-server/rerank_server_ane.py": ("duplicate", "superseded-by: tools/rerank-server/rerank_server.py (GPU lane); ANE-lane variant kept", "ANE AOT twin — NOT merged (149/220 lines differ: host-side RoPE + last-token one-hot + 32-wide head + AOT .aimodelc load). Its artifact work/exports/reranker-ane/ is absent from this box, so merge-equivalence is unprovable — same honest category as embed_server_gemma.py. 2026-10 audit."),
    "tools/rerank-server/gate_reranker.py": ("canonical", "reranker gate — JIT lane", "Drift found 2026-10: expects ref[\"seq_len\"] but models/qwen3-reranker/reference.json lost that key; .aimodel also absent so repair is unprovable. Documented, not patched blind. ANE twin: bench/gate_reranker_ane.py."),
    "tools/memory-stack/start.sh": ("canonical", "local memory stack launcher", ""),
    "tools/archive/inventory.py":  ("superseded", "", "Produced knowledge/ane/ARCHIVE-MAP.md; regenerate before reuse."),
    "tools/granite-runner/Package.swift": ("canonical", "Core AI gate runner (Swift, granite)", ""),
    "tools/audit/smoke.py":        ("canonical", "audit phase-1 smoke driver", "Artifact of the 2026-10 tool audit."),
    "tools/audit/build_census.py": ("canonical", "audit census builder", ""),
    "tools/audit/verdicts.py":     ("canonical", "audit verdict engine (this file)", ""),
    # ================= results/EXP-002 =================
    "results/EXP-002-apple-fm-baseline/harness/p2_fm_lane_audit.sh": ("superseded", "", E),
    # ================= results/EXP-025 — ANE/GPU sync RE =================
    "results/EXP-025-ane-gpu-sync/harness/ane_bridge.h": ("canonical", "ANE private-API bridge header", "Bridge pair twins: _dbg.m (event logging) and _mrr.m (MRR variant)."),
    "results/EXP-025-ane-gpu-sync/harness/ane_bridge_dbg.m": ("duplicate", "superseded-by: results/EXP-025-ane-gpu-sync/harness/ane_bridge.h", "Event-logging twin of ane_bridge_mrr.m; bridge header is the instrument."),
    "results/EXP-025-ane-gpu-sync/harness/ane_bridge_mrr.m": ("duplicate", "superseded-by: results/EXP-025-ane-gpu-sync/harness/ane_bridge.h", "MRR twin of ane_bridge_dbg.m."),
    "results/EXP-025-ane-gpu-sync/harness/ane_class_dump.m": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/ane_reqmethods.m": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/ane_surface_probe.m": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/ane_sync_harness.m": ("superseded", "", "Sync prototype; conclusion (IOSurfaceSharedEvent works) in EXP-025 README. " + E),
    "results/EXP-025-ane-gpu-sync/harness/chain_harness.m": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/coreml_explore_ops.py": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/coreml_image_probe.m": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/coreml_plan.m": ("superseded", "", "Superseded by coreml_plan.py + plan_devicesupport.m (both canonical). " + E),
    "results/EXP-025-ane-gpu-sync/harness/coreml_run.m": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/coreml_run.py": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/coreml_walk.m": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/inspect.lldb": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/inspect.sh": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/join_chain.m": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/make_conv.py": ("superseded", "", "Graph-builder family; current generator: EXP-029 make_gemm_models.py. " + E),
    "results/EXP-025-ane-gpu-sync/harness/make_dtype_test.py": ("superseded", "", "Graph-builder family. " + E),
    "results/EXP-025-ane-gpu-sync/harness/make_graph.py": ("superseded", "", "Graph-builder family. " + E),
    "results/EXP-025-ane-gpu-sync/harness/make_mixed.py": ("superseded", "", "Graph-builder family. " + E),
    "results/EXP-025-ane-gpu-sync/harness/make_mlmodelc.py": ("superseded", "", "Graph-builder family. " + E),
    "results/EXP-025-ane-gpu-sync/harness/make_split.py": ("superseded", "", "Graph-builder family. " + E),
    "results/EXP-025-ane-gpu-sync/harness/mini.m": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/ops_battery.py": ("superseded", "", "ANE op-enum done — map now in EXP-001 + KB. " + E),
    "results/EXP-025-ane-gpu-sync/harness/p2_enginemon_loop.sh": ("superseded", "", "enginemon now ships as tools/enginemon (canonical). " + E),
    "results/EXP-025-ane-gpu-sync/harness/p2_kane_scan.c": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/p2_kane_strings.m": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/p2_mlmodel_probe.m": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/p2_shim_open.c": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/p2_sudo_capture.sh": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/patch_pathb.py": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/pkgb_harness.m": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/plan_flip_sweep.sh": ("superseded", "", "Placement-flip sweep answered; table in EXP-025 README / coreml_route_sweep.py. " + E),
    "results/EXP-025-ane-gpu-sync/harness/plan_hw_sweep.sh": ("superseded", "", "Same family as plan_flip_sweep.sh. " + E),
    "results/EXP-025-ane-gpu-sync/harness/plan_mac_probe.py": ("superseded", "", "Same family. " + E),
    "results/EXP-025-ane-gpu-sync/harness/trace_ane_attach.sh": ("superseded", "", E),
    "results/EXP-025-ane-gpu-sync/harness/trace_primary.sh": ("superseded", "", E),
    # ================= results/EXP-026 — ANE kitchen =================
    "results/EXP-026-ane-kitchen/harness/p2b_compile.m": ("canonical", "minimal public compile helper (CLT-only)", "Only public-face MIL compile path without full Xcode; still reusable."),
    "results/EXP-026-ane-kitchen/harness/p2b_compiler_probe.m": ("superseded", "", E),
    "results/EXP-026-ane-kitchen/harness/p2b_fw_probe.m": ("superseded", "", E),
    "results/EXP-026-ane-kitchen/harness/p2b_mila_abi.m": ("superseded", "", "ABI archaeology; refined by EXP-027 p27_mila_abi2. " + E),
    "results/EXP-026-ane-kitchen/harness/p2b_mila_file.m": ("superseded", "", E),
    "results/EXP-026-ane-kitchen/harness/p2b_milaneflow_probe.m": ("superseded", "", E),
    "results/EXP-026-ane-kitchen/harness/p2b_milgen.py": ("canonical", "MIL conv-chain generator (proven on 27.0.1)", "For cross-lane GEMM models prefer EXP-029 make_gemm_models.py."),
    "results/EXP-026-ane-kitchen/harness/p2b_mlir_bc_strings.py": ("superseded", "", "Superseded by bench/mlir_bytecode.py. " + E),
    "results/EXP-026-ane-kitchen/harness/p2b_mps_dialect_build.sh": ("superseded", "", E),
    "results/EXP-026-ane-kitchen/harness/p2b_sudo_capture_v7.sh": ("superseded", "", E),
    "results/EXP-026-ane-kitchen/harness/p2b_sudo_capture_v8.sh": ("superseded", "", E),
    "results/EXP-026-ane-kitchen/harness/p2b_xpc_client.m": ("superseded", "", E),
    # ================= results/EXP-027 — NAX =================
    "results/EXP-027-nax/harness/p27_anpos_capture.sh": ("superseded", "", "AN-POS calibration done; promoted table in README + API-128. " + E),
    "results/EXP-027-nax/harness/p27_anpos_promote.sh": ("superseded", "", "Same episode. " + E),
    "results/EXP-027-nax/harness/p27_anpos_run.py": ("superseded", "", "Same episode. " + E),
    "results/EXP-027-nax/harness/p27_es_harness.m": ("superseded", "", E),
    "results/EXP-027-nax/harness/p27_load_coreai.py": ("canonical", "sustained matmul2d lane load (coreai route)", "Feeds EXP-029/EXP-028 window queue as the load generator."),
    "results/EXP-027-nax/harness/p27_load_msl.m": ("canonical", "sustained plain-MSL GPU load (matched SIMT arm)", "EXP-029 arm-3 load generator."),
    "results/EXP-027-nax/harness/p27_m2d_xcode_probe.metal": ("superseded", "", "Compile probe; Xcode-27 answer recorded, MetalHLO is the working route. " + E),
    "results/EXP-027-nax/harness/p27_mila_abi2.m": ("superseded", "", E),
    "results/EXP-027-nax/harness/p27_nax_probe.m": ("superseded", "", E),
    "results/EXP-027-nax/harness/p27_nxd_analyze.py": ("canonical", "enginemon full-channel window diff", "Reusable lens for any future channel question."),
    "results/EXP-027-nax/harness/p27_nxd_capture.sh": ("canonical", "unfiltered enginemon capture windows", "Pair with p27_nxd_analyze.py."),
    "results/EXP-027-nax/harness/p27_src_probe.m": ("superseded", "", E),
    "results/EXP-027-nax/harness/p27_stale_probe.m": ("superseded", "", E),
    # ================= results/EXP-028 — Apple tracer (ACTIVE, window-queued) =====
    "results/EXP-028-apple-tracer/harness/p28_capture.sh": ("canonical", "apple-tracer capture driver (rescoped 0x238+0x1b8)", "Active: awaiting quiet window."),
    "results/EXP-028-apple-tracer/harness/p28_e1_signpost.sh": ("canonical", "os-log/signpost capture around Core AI runs", "Active: EXP-028 E1."),
    "results/EXP-028-apple-tracer/harness/p28_coreai_run/main.swift": ("canonical", "Core AI load runner for tracer windows (Swift)", "Active: the load the tracer watches; registered 2026-10-11 (was a harness-subdir blind spot)."),
    # ================= results/EXP-029 additions =================
    "results/EXP-029-nax-crosslane/harness/nax_ladder.metal": ("superseded", "", "Ladder kernel companion; working kernel embedded in p27_r8.m (canonical). " + E),
    "results/EXP-029-nax-crosslane/harness/power_correlate.sh": ("canonical", "GPU-power attribution by process", "Needs sudo window for joule attribution; unprivileged pass works."),
    # ================= scratch (../exp022-raw) =================
    "../exp022-raw/clean_capture.sh": ("scratch", "", "EXP-022 one-shot capture wrapper; raw evidence stays in place."),
    "../exp022-raw/final_capture.sh": ("scratch", "", "EXP-022 one-shot capture wrapper."),
    "../exp022-raw/s4_rerun.sh": ("scratch", "", "EXP-022 one-shot S4 rerun."),
    "../exp022-raw/t8_gate_quiet.sh": ("scratch", "", "EXP-022/023 quiet-gate check; superseded in spirit by EXP-029 quiet_probe.sh."),
    "../exp022-raw/t8_latency.sh": ("scratch", "", "EXP-023 T8 latency rerun wrapper."),
}


def emit() -> int:
    rows = []
    for path, (status, for_, note) in sorted(V.items()):
        if path == "bench/smoke-audit-driver":
            continue
        rows.append({"path": path, "status": status, "canonical_for": for_, "note": note})
    JSONL.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    print(f"emitted {len(rows)} verdicts -> {JSONL.relative_to(ROOT)}")
    return 0


def check() -> int:
    reg = {}
    for line in (ROOT / "tools" / "instruments.jsonl").read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            reg[r["path"]] = r
    missing = [p for p, r in reg.items()
               if r.get("status") == "unclassified" and p not in V]
    canon_dupes = [k for k in V if k in reg and reg[k].get("status") != "unclassified"
                   and k in ("bench/", )]
    print(f"verdicts cover {len([p for p in V if p in reg and p not in ('bench/smoke-audit-driver',)])} "
          f"of {len([p for p,r in reg.items() if r.get('status')=='unclassified'])} unclassified")
    if missing:
        print("MISSING verdicts for:")
        for p in missing:
            print(f"  {p}")
        return 1
    print("all currently-unclassified entries have verdicts")
    return 0


if __name__ == "__main__":
    if "--emit" in sys.argv:
        sys.exit(emit())
    sys.exit(check())
