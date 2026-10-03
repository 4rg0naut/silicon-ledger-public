#!/usr/bin/env python3
"""Build / maintain results/measurements.json from a compact source table.

The committed measurements.json is the single source of truth and is NOT
regenerable from this table alone: it also holds the verified-extracted rows
(merged by bench/verify_extraction.py from fragments that are ephemeral, not
in this repo). So this tool is NON-DESTRUCTIVE by default:

  default         validate the table + ledger, report shared/new/drift, and
                  leave measurements.json BYTE-IDENTICAL
  --apply-new     append ROW ids that are not yet in the ledger
  --force         also overwrite shared ids with the ROWS values
  (no file)       fresh build from ROWS only

Re-curation of a row that is already in the ledger is reported as drift and
applied only with --force; a ROW removed from this table does NOT remove the
ledger record. Adding a row is still one tuple (22 fields through
provenance/date/command, or all 26 with the energy slots).
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "measurements.json"

M4 = "Apple M4 (h16g), 16 GB"
M4MAX = "Apple M4 Max"
RYZEN = "AMD Ryzen 5 3600, 4 threads"
# id, model, checkpoint, params_m, runtime, placement, dtype, seq_len, regions,
#   benchmark, split, scope, tiers, metric, value, unit,
#   latency_ms, latency_unit, hardware, provenance, date, command
ROWS = [
    # ---------------- decision models: JevBench v1.3.0 ----------------
    ("laya-en-ane-s256", "Laya English (ModernBERT-large)", "convaiinnovations/laya", 421,
     "Core AI", "ANE", "fp16", 256, 2, "JevBench v1.3.0", "public", "231 of 534", "easy+standard+hard",
     "Intelligence", 41.5, "chance-corrected 0-100", 68.1, "per decision (all options, one pass)", M4,
     "ours", "2026-09-22", "bench/jevbench_ane.py + laya_ane_bench.py"),
    ("laya-en-cpu-published", "Laya English (ModernBERT-large)", "convaiinnovations/laya", 421,
     "CPU", "CPU", "fp32", 512, None, "JevBench v1.3.0", "full", "534 items", "easy+standard+judge+hard",
     "Intelligence", 45.8, "chance-corrected 0-100", 790.0, "per decision", RYZEN,
     "third-party (JevBench v1.3.0 #33)", "2026-09-21", "jevbench/adapters/laya_local.py"),
    ("von-ane-s256", "Von-1.0 (ModernBERT-large, NLI)", "wfzyx/von", 395,
     "Core AI", "ANE", "fp16", 256, 3, "JevBench v1.3.0", "public", "231 of 534", "easy+standard+hard",
     "Intelligence", 36.2, "chance-corrected 0-100", 105.0, "per decision (N option passes)", M4,
     "ours", "2026-09-22", "bench/jevbench_ane.py (VonANEAdapter)"),
    ("von-cpu-s256", "Von-1.0 (ModernBERT-large, NLI)", "wfzyx/von", 395,
     "Core AI", "CPU", "fp16", 256, None, "JevBench v1.3.0", "public", "231 of 534", "easy+standard+hard",
     "Intelligence", 36.2, "chance-corrected 0-100", 98.0, "per decision (N option passes)", M4,
     "ours", "2026-09-22", "bench/jevbench_ane.py --compute cpu"),
    ("laya-ml-ane-s1024", "Laya-multilingual (mmBERT-base)", "convaiinnovations/laya-multilingual", 149,
     "Core AI", "ANE", "fp16", 1024, 2, "JevBench v1.3.0", "public", "231 of 534", "easy+standard+hard",
     "Intelligence", 22.3, "chance-corrected 0-100", 106.8, "per decision (all options, one pass)", M4,
     "ours", "2026-09-22", "bench/jevbench_ane.py --model-dir models/laya-multilingual"),

    # ---------------- embedders: MTEB SciFact / NFCorpus ----------------
    ("granite97m-ane-scifact", "Granite-Embedding-97M", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "ANE", "fp16", 512, 1, "MTEB SciFact", "test", "full", None,
     "ndcg@10", 0.68546, "ndcg@10", 2.14, "per embedding", M4,
     "ours", "2026-09-20", "bench/granite_ane_variants.py"),
    ("minilm-l6-scifact", "all-MiniLM-L6", "sentence-transformers/all-MiniLM-L6-v2", 22,
     None, None, None, None, None, "MTEB SciFact", "test", "full", None,
     "ndcg@10", 0.64508, "ndcg@10", None, None, None,
     "third-party (MTEB)", None, None),
    ("bge-small-scifact", "bge-small-en-v1.5", "BAAI/bge-small-en-v1.5", 33,
     None, None, None, None, None, "MTEB SciFact", "test", "full", None,
     "ndcg@10", 0.71273, "ndcg@10", None, None, None,
     "third-party (MTEB)", None, None),
    ("bge-base-scifact", "bge-base-en-v1.5", "BAAI/bge-base-en-v1.5", 110,
     None, None, None, None, None, "MTEB SciFact", "test", "full", None,
     "ndcg@10", 0.74345, "ndcg@10", None, None, None,
     "third-party (MTEB)", None, None),
    ("mpnet-base-scifact", "mpnet-base", "sentence-transformers/all-mpnet-base-v2", 110,
     None, None, None, None, None, "MTEB SciFact", "test", "full", None,
     "ndcg@10", 0.65570, "ndcg@10", None, None, None,
     "third-party (MTEB)", None, None),
    ("granite97m-ane-nfcorpus", "Granite-Embedding-97M", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "ANE", "fp16", 512, 1, "MTEB NFCorpus", "test", "full", None,
     "ndcg@10", 0.29470, "ndcg@10", None, "per embedding", M4,
     "ours", "2026-09-20", "bench/granite_ane_variants.py"),
    ("granite97m-ane-french", "Granite-Embedding-97M", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "ANE", "fp16", 512, 1, "MTEB (French subset)", "test", "full", None,
     "ndcg@10", 0.6551, "ndcg@10", None, "per embedding", M4,
     "ours", "2026-09-21", "bench/mteb_french_tasks.py"),
    ("e5-small-french", "multilingual-e5-small", "intfloat/multilingual-e5-small", 118,
     None, None, None, None, None, "MTEB (French subset)", "test", "full", None,
     "ndcg@10", 0.6334, "ndcg@10", None, None, None,
     "third-party (MTEB)", None, None),

    # ---------------- reranker + pipeline ----------------
    ("qwen3-reranker-ane", "Qwen3-Reranker-0.6B", "Qwen/Qwen3-Reranker-0.6B", 600,
     "Core AI", "ANE", "fp16", 512, 1, "SciFact (BEIR)", "test", "full", None,
     "ndcg@10 delta", 0.07861, "absolute delta over retriever order", None, None, M4,
     "ours", "2026-09-21", "bench/gate_reranker_ane.py"),
    ("pipeline-ours-reranked", "Granite-97M chunk-indexed + Qwen3-Reranker", "see EXP-014", 97,
     "Core AI", "ANE", "fp16", 512, 1, "SciFact (BEIR)", "test", "full", None,
     "ndcg@10", 0.75860, "ndcg@10", None, None, M4,
     "ours", "2026-09-21", "bench/rerank_retrieval.py"),
    ("pipeline-bgebase-reranked", "bge-base-en-v1.5 + Qwen3-Reranker", "BAAI/bge-base-en-v1.5", 109,
     None, None, None, None, None, "SciFact (BEIR)", "test", "full", None,
     "ndcg@10", 0.77204, "ndcg@10", None, None, None,
     "ours (same reranker, swapped retriever)", "2026-09-21", "bench/rerank_retrieval.py"),

    # ---------------- ANE encoder ports: residency + speed ----------------
    ("minilm-coreml-ane", "all-MiniLM-L6-v2 (Core ML)", "sentence-transformers/all-MiniLM-L6-v2", 22,
     "Core ML", "ANE (compute_units=ALL)", "fp16", 128, None, "latency microbench", None, "128-token encodes", None,
     "throughput", 1363.0, "embeddings/s", 0.73, "per embedding (mean)", M4,
     "ours", "2026-09-20", "bench/bench_encoder.py"),
    ("minilm-coreml-cpu", "all-MiniLM-L6-v2 (Core ML)", "sentence-transformers/all-MiniLM-L6-v2", 22,
     "Core ML", "CPU_ONLY", "fp16", 128, None, "latency microbench", None, "128-token encodes", None,
     "throughput", 597.0, "embeddings/s", 1.68, "per embedding (mean)", M4,
     "ours", "2026-09-20", "bench/bench_encoder.py"),
    ("minilm-coreml-gpu", "all-MiniLM-L6-v2 (Core ML)", "sentence-transformers/all-MiniLM-L6-v2", 22,
     "Core ML", "CPU_AND_GPU", "fp16", 128, None, "latency microbench", None, "128-token encodes", None,
     "throughput", 480.0, "embeddings/s", 2.08, "per embedding (mean)", M4,
     "ours", "2026-09-20", "bench/bench_encoder.py"),
    ("granite97m-fp16-13reg", "Granite-Embedding-97M fp16 (as exported)", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "ANE", "fp16", 128, 13, "latency microbench", None, "4000 warm iterations", None,
     "latency", 13.19, "ms", 13.19, "per embedding", M4,
     "ours", "2026-09-20", "bench/granite_ane_variants.py"),
    ("granite97m-fp16-1reg", "Granite-Embedding-97M fp16 + 2 fp32-op removals", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "ANE", "fp16", 128, 1, "latency microbench", None, "4000 warm iterations", None,
     "latency", 4.60, "ms", 4.60, "per embedding", M4,
     "ours", "2026-09-20", "bench/granite_ane_variants.py"),
    ("granite97m-fp32-0reg", "Granite-Embedding-97M fp32 (published)", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "GPU (silent fallback)", "fp32", 128, 0, "latency microbench", None, "4000 warm iterations", None,
     "latency", 4.31, "ms", 4.31, "per embedding", M4,
     "ours", "2026-09-20", "coreai-build compile --preferred-compute neural-engine"),
    ("granite97m-w8", "Granite-Embedding-97M w8", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "ANE", "int8-affine + fp16", 128, 13, "MTEB SciFact", "test", "full", None,
     "ndcg@10", 0.68546, "ndcg@10", 19.48, "per embedding", M4,
     "ours", "2026-09-20", "bench/export_granite_w8_fp16.py --bits 8"),
    ("granite97m-w6", "Granite-Embedding-97M w6", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "ANE", "int6-affine + fp16", 128, 14, "MTEB SciFact", "test", "full", None,
     "ndcg@10", None, "ndcg@10 (FAILED the gate: min cosine 0.9983865)", None, None, M4,
     "ours", "2026-09-20", "bench/export_granite_w8_fp16.py --bits 6"),
    ("granite97m-w4", "Granite-Embedding-97M w4", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "none (won't compile)", "int4-affine + fp16", 128, 0, "MTEB SciFact", "test", "full", None,
     "ndcg@10", None, "ndcg@10 (FAILED: 16 pair flips)", None, None, M4,
     "ours", "2026-09-20", "bench/export_granite_w8_fp16.py --bits 4"),
    ("laya-ml-ane-s256", "Laya-multilingual (mmBERT-base)", "convaiinnovations/laya-multilingual", 149,
     "Core AI", "ANE", "fp16", 256, 2, "latency microbench", None, "231 decisions", None,
     "latency", 11.83, "ms", 11.83, "per decision (all options, one pass)", M4,
     "ours", "2026-09-22", "bench/laya_ane_bench.py"),
    ("von-ane-v0", "Von-1.0 v0 (fp32 softmax)", "wfzyx/von", 395,
     "Core AI", "ANE", "fp16", 256, 31, "latency microbench", None, "5 cases", None,
     "latency", 74.0, "ms", 74.0, "per decision (N option passes)", M4,
     "ours", "2026-09-22", "bench/export_von_ane.py --variant v0"),
    ("von-ane-v1", "Von-1.0 v1 (softmax in graph dtype)", "wfzyx/von", 395,
     "Core AI", "ANE", "fp16", 256, 3, "latency microbench", None, "5 cases", None,
     "latency", 24.0, "ms", 24.0, "per decision (N option passes)", M4,
     "ours", "2026-09-22", "bench/export_von_ane.py --variant v1"),

    # ---------------- Core AI placement (EXP-004) ----------------
    ("granite97m-coreai-cpuonly", "Granite-Embedding-97M", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "cpuOnly", "fp32", 128, None, "latency microbench", None, "warm median", None,
     "latency", 8.28, "ms", 8.28, "per embedding", M4,
     "ours", "2026-09-20", "tools/granite-runner"),
    ("granite97m-coreai-gpu", "Granite-Embedding-97M", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "gpu", "fp32", 128, None, "latency microbench", None, "warm median", None,
     "latency", 6.06, "ms", 6.06, "per embedding", M4,
     "ours", "2026-09-20", "tools/granite-runner"),
    ("granite97m-coreai-ane", "Granite-Embedding-97M", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
     "Core AI", "neuralEngine", "fp32", 128, 0, "latency microbench", None, "warm median", None,
     "latency", 4.33, "ms", 4.33, "per embedding", M4,
     "ours", "2026-09-20", "tools/granite-runner"),

    # ---------------- ANE dtype probe (EXP-005) ----------------
    ("tiny-fp16", "tiny probe (ANE-shaped)", "n/a", None,
     "Core AI", "ANE", "fp16", None, 66, "dtype control", None, "trivial graph", None,
     "ANE regions", 66.0, "regions", None, None, M4,
     "ours", "2026-09-20", "bench/probe_ane_regions.py"),
    ("tiny-fp32", "tiny probe (ANE-shaped)", "n/a", None,
     "Core AI", "none", "fp32", None, 0, "dtype control", None, "trivial graph", None,
     "ANE regions", 0.0, "regions", None, None, M4,
     "ours", "2026-09-20", "bench/probe_ane_regions.py"),

    # ---------------- energy ----------------
    ("laya-en-ane-energy", "Laya English (ModernBERT-large)", "convaiinnovations/laya", 421,
     "Core AI", "ANE", "fp16", 512, 2, "energy microbench", None, "432 decisions", None,
     "GPU power", 15.9, "mW", None, None, M4,
     "ours", "2026-09-22", "tools/enginemon/enginemon -- <adapter>"),

    # ---------------- grid sweep (EXP-009) ----------------
    *[(f"grid-{g}", "Granite-Embedding-97M", "ibm-granite/granite-embedding-97m-multilingual-r2", 97,
       "Core AI", "ANE", "fp16", g, 1, "MTEB SciFact", "test", "full", None,
       "ndcg@10", v, "ndcg@10", None, None, M4,
       "ours", "2026-09-20", "bench/mteb_retrieval.py")
      for g, v in ((64, 0.59060), (128, 0.65176), (256, 0.67622), (512, 0.68546), (1024, 0.68760))],
]

# Every row must say what it measured and where the number comes from. Rows WE
# ran must additionally say WHEN and HOW — date and command are the substance
# of reproducibility, and no row we ran lacks them. runtime/placement/dtype
# stay in the schema's mandatory-but-nullable set (results_table.py --gaps
# prints them as gaps) because hybrid rows (e.g. a third-party retriever plus
# our ANE reranker) have no single runtime to name, and forcing one would be
# false precision — the ledger's rule is null = NOT MEASURED, printed, never
# invented. Third-party leaderboard rows have no date/command of ours either.
MANDATORY = ("id", "model", "benchmark", "metric", "value", "unit", "provenance")
MANDATORY_OURS = MANDATORY + ("date", "command")
KEYS = ("id", "model", "checkpoint", "params_m", "runtime", "placement", "dtype", "seq_len",
        "ane_regions", "benchmark", "split", "scope", "tiers", "metric", "value", "unit",
        "latency_ms", "latency_unit", "hardware", "load_factor", "energy_mw", "energy_rail",
        "energy_baseline", "provenance", "date", "command")
SCHEMA_NOTE = "bench/results_table.py — every field is mandatory; null means NOT MEASURED and prints as an em-dash"
BASE_NOTE = ("Built by bench/build_measurements.py. Rows are ranked only when "
             "benchmark+split+scope+tiers+metric+unit+latency_unit all agree.")


def expand(r: tuple) -> tuple:
    """Map a ROWS tuple onto the 26-field KEYS schema.

    The table rows carry 22 fields: everything through `hardware`, then
    provenance/date/command. The schema has four slots between hardware and
    provenance (load_factor, energy_mw, energy_rail, energy_baseline) that are
    NOT MEASURED for these rows — pad them with None. A row that already
    carries all 26 fields passes through untouched. Anything else is a
    builder bug and is rejected loudly, because a silently shifted row
    mislabels its provenance.
    """
    if len(r) == len(KEYS):
        return r
    if len(r) == 22:
        return r[:19] + (None, None, None, None) + r[19:]
    raise SystemExit(f"row {r[0]!r}: expected {len(KEYS)} or 22 fields, got {len(r)}")


def build_rows() -> list[dict]:
    recs = []
    for r in ROWS:
        d = dict(zip(KEYS, expand(r)))
        required = MANDATORY_OURS if str(d.get("provenance") or "").startswith("ours") else MANDATORY
        missing = [k for k in required if d.get(k) in (None, "") and k != "value"]
        # A measured non-result: the row exists to record that a number does NOT
        # exist (the gate failed before the task ran). That is allowed, but only
        # when the unit field says so — a bare null value is a silent gap.
        if d.get("value") in (None, "") and "FAILED" not in str(d.get("unit") or "").upper():
            missing.append("value")
        if missing:
            raise SystemExit(f"{d['id']}: missing mandatory {missing}")
        recs.append({k: d.get(k) for k in KEYS})
    return recs


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply-new", action="store_true",
                    help="append ROW ids that are not yet in the existing file")
    ap.add_argument("--force", action="store_true",
                    help="overwrite existing records with the ROWS values "
                         "(default: existing records are authoritative and never touched)")
    args = ap.parse_args()

    recs = build_rows()
    by_row = {r["id"]: r for r in recs}
    if len(by_row) != len(recs):
        dupes = sorted({r["id"] for r in recs if [x["id"] for x in recs].count(r["id"]) > 1})
        raise SystemExit(f"ROWS table has duplicate ids: {dupes}")

    if not OUT.exists():
        OUT.write_text(json.dumps({"_schema": SCHEMA_NOTE, "_note": BASE_NOTE,
                                   "measurements": recs}, indent=1))
        print(f"  wrote {len(recs)} records (fresh build) -> {OUT.relative_to(ROOT)}")
        return 0

    cur = json.loads(OUT.read_text())
    existing = {m["id"]: m for m in cur["measurements"]}
    if len(existing) != len(cur["measurements"]):
        raise SystemExit(f"{OUT.name}: duplicate ids in the existing file — "
                         "refusing to merge into an inconsistent ledger")

    shared = sorted(set(by_row) & set(existing))
    new = sorted(set(by_row) - set(existing))
    drift = [(rid, k, existing[rid].get(k), by_row[rid].get(k))
             for rid in shared for k in KEYS
             if existing[rid].get(k) != by_row[rid].get(k)]

    if not (args.apply_new or args.force):
        # Default: validate the table and the ledger, report, and leave the file
        # BYTE-IDENTICAL. The committed file is the source of truth; its records
        # (including verified-extracted rows that no longer live in ROWS) are
        # never overwritten or dropped by this tool. Re-curation is reported as
        # drift and applied only with an explicit flag.
        print(f"  existing ledger  : {len(existing)} records — UNTOUCHED (byte-identical)")
        print(f"  ROWS table       : {len(recs)} rows — {len(shared)} ids shared with the ledger, "
              f"{len(new)} new")
        if drift:
            ids = sorted({d[0] for d in drift})
            print(f"  drift            : {len(drift)} fields on {len(ids)} shared ids "
                  f"(ledger values authoritative; rows shown for review, NOT applied):")
            for rid, k, a, b in drift[:20]:
                print(f"    {rid}.{k}: ledger={a!r}  rows={b!r}")
            if len(drift) > 20:
                print(f"    … and {len(drift)-20} more")
        if new:
            print(f"  new ids          : {', '.join(new)} (apply with --apply-new)")
        print("  safety           : no record in the ledger is overwritten or dropped "
              "without --force; a removed ROW does not remove a ledger record.")
        return 0

    merged = [dict(m) for m in cur["measurements"]]
    pos = {m["id"]: i for i, m in enumerate(merged)}
    added = overwritten = 0
    for r in recs:
        if r["id"] in pos:
            if args.force:
                merged[pos[r["id"]]] = r
                overwritten += 1
        else:
            merged.append(r)
            added += 1
    cur["measurements"] = merged
    OUT.write_text(json.dumps(cur, indent=1))
    print(f"  merged -> {len(merged)} records (+{added} added, {overwritten} overwritten, "
          f"existing order preserved) -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
