#!/usr/bin/env python3
"""Merge silicon-ledger-bench claim rows into results/measurements.json.

The raw-hardware corpus is produced by the sibling repo silicon-ledger-bench
(public; schema id `silicon-ledger/1`; join keys per CROSS-REPO-CONTRACT.md).
This tool reads one bench report JSON and maps its run data onto the claim
rows declared in REPRODUCE.md — one ledger row per claim, value taken
verbatim from the report and only rounded as REPRODUCE declares.

Safety model is identical to build_measurements.py:
  default   validate report + ledger, report shared/new, leave file BYTE-IDENTICAL
  --apply   append claim ids that are not yet in the ledger
The committed file is the source of truth: no existing record is overwritten
or dropped, and a claim already in the ledger is reported, not re-applied.

usage:
    python3 bench/import_bench_reports.py <report.json>
    python3 bench/import_bench_reports.py <report.json> --apply
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
from results_table import FIELDS  # noqa: E402  (single source of truth for the schema)

OUT = ROOT / "results" / "measurements.json"

# These claim rows are machine-specific: the fingerprint/chip check below
# rejects any report that is not the declared machine.
EXPECTED_CHIP = "Apple M5 Max"
HARDWARE = "Apple M5 Max (h17c), 128 GB"  # 2026-10-06: CoreAI arch correction, EXP-023
MODEL = "Apple M5 Max"
CHECKPOINT = "silicon-ledger-bench v0.1"

# value: ("derived", key) | ("median",) — taken verbatim from the report run.
# nd:    REPRODUCE.md's declared rounding; the stored value must equal round(raw, nd).
CLAIMS = [
    # ---- S1 memory (GB/s) ----
    dict(id="m5max-s1-gpu-read",   run="gpu_read",   variant=None,     value=("derived", "GBs"), nd=1,
         suite="s1_memory", bench="silicon-ledger-bench S1 (memory)", command="bench memory",
         metric="bandwidth", unit="GB/s", unit_kind="gb", dtype="fp32 buffers",
         runtime="Metal", placement="GPU", scope="256 MB GPU, steady state after primer"),
    dict(id="m5max-s1-gpu-write",  run="gpu_write",  variant=None,     value=("derived", "GBs"), nd=1,
         suite="s1_memory", bench="silicon-ledger-bench S1 (memory)", command="bench memory",
         metric="bandwidth", unit="GB/s", unit_kind="gb", dtype="fp32 buffers",
         runtime="Metal", placement="GPU", scope="256 MB GPU, steady state after primer"),
    dict(id="m5max-s1-gpu-copy",   run="gpu_copy",   variant=None,     value=("derived", "GBs"), nd=1,
         suite="s1_memory", bench="silicon-ledger-bench S1 (memory)", command="bench memory",
         metric="bandwidth", unit="GB/s", unit_kind="gb", dtype="fp32 buffers",
         runtime="Metal", placement="GPU", scope="256 MB GPU, steady state after primer"),
    dict(id="m5max-s1-gpu-triad",  run="gpu_triad",  variant=None,     value=("derived", "GBs"), nd=1,
         suite="s1_memory", bench="silicon-ledger-bench S1 (memory)", command="bench memory",
         metric="bandwidth", unit="GB/s", unit_kind="gb", dtype="fp32 buffers",
         runtime="Metal", placement="GPU", scope="256 MB GPU, steady state after primer"),
    dict(id="m5max-s1-cpu-read",   run="cpu_read",   variant=None,     value=("derived", "GBs"), nd=1,
         suite="s1_memory", bench="silicon-ledger-bench S1 (memory)", command="bench memory",
         metric="bandwidth", unit="GB/s", unit_kind="gb", dtype="fp32 buffers",
         runtime="vDSP (18 cores)", placement="CPU", scope="512 MB CPU"),
    dict(id="m5max-s1-cpu-write",  run="cpu_write",  variant=None,     value=("derived", "GBs"), nd=1,
         suite="s1_memory", bench="silicon-ledger-bench S1 (memory)", command="bench memory",
         metric="bandwidth", unit="GB/s", unit_kind="gb", dtype="fp32 buffers",
         runtime="vDSP (18 cores)", placement="CPU",
         scope="512 MB CPU, low band (external memory pressure; bimodal, REPRODUCE trap R9)"),
    dict(id="m5max-s1-cpu-triad",  run="cpu_triad",  variant=None,     value=("derived", "GBs"), nd=1,
         suite="s1_memory", bench="silicon-ledger-bench S1 (memory)", command="bench memory",
         metric="bandwidth", unit="GB/s", unit_kind="gb", dtype="fp32 buffers",
         runtime="vDSP (18 cores)", placement="CPU", scope="512 MB CPU"),
    dict(id="m5max-s1-tensor-copy", run="tensor_copy", variant=None,   value=("derived", "GBs"), nd=1,
         suite="s1_memory", bench="silicon-ledger-bench S1 (memory)", command="bench memory",
         metric="bandwidth", unit="GB/s", unit_kind="gb", dtype="fp32 tensor",
         runtime="MTL4 tensor encoder", placement="GPU", scope="256 MB fp32 tensor (native tensor copy path)"),
    # ---- S2 GEMM (GFLOPS) ----
    dict(id="m5max-s2-gemm8192-fp16-mps", run="gemm_8192_fp16", variant="mps", value=("derived", "GFLOPS"), nd=0,
         suite="s2_gemm", bench="silicon-ledger-bench S2 (GEMM)", command="bench gemm",
         metric="GEMM throughput", unit="GFLOPS", unit_kind="ops", dtype="fp16",
         runtime="MPS", placement="GPU", scope="n=8192, torch-validated, median of 30"),
    dict(id="m5max-s2-gemm8192-fp32-mps", run="gemm_8192_fp32", variant="mps", value=("derived", "GFLOPS"), nd=0,
         suite="s2_gemm", bench="silicon-ledger-bench S2 (GEMM)", command="bench gemm",
         metric="GEMM throughput", unit="GFLOPS", unit_kind="ops", dtype="fp32",
         runtime="MPS", placement="GPU", scope="n=8192, torch-validated, median of 30"),
    dict(id="m5max-s2-gemm8192-bf16-msl", run="gemm_8192_bf16", variant="msl", value=("derived", "GFLOPS"), nd=0,
         suite="s2_gemm", bench="silicon-ledger-bench S2 (GEMM)", command="bench gemm",
         metric="GEMM throughput", unit="GFLOPS", unit_kind="ops", dtype="bf16",
         runtime="MSL (custom kernel)", placement="GPU", scope="n=8192, torch-validated, median of 30"),
    dict(id="m5max-s2-gemm8192-int8-mps", run="gemm_8192_int8", variant="mps", value=("derived", "GFLOPS"), nd=0,
         suite="s2_gemm", bench="silicon-ledger-bench S2 (GEMM)", command="bench gemm",
         metric="GEMM throughput", unit="GFLOPS", unit_kind="ops", dtype="int8",
         runtime="MPS", placement="GPU", scope="n=8192, torch-validated, median of 30"),
    # ---- S3 ANE raw (private API) ----
    dict(id="m5max-s3-dispatch-floor", run="dispatch_floor", variant=None, value=("median",), nd=3,
         suite="s3_ane_raw", bench="silicon-ledger-bench S3 (ANE raw, private API)",
         command="bench spike && bench ane",
         metric="ANE latency", unit="ms/eval", unit_kind="ms", dtype="fp32 IO",
         runtime="ANE (_ANEInMemoryModel)", placement="ANE",
         scope="256ch x 1d x 64sp, dispatch-only subset, 100 iters", latency=True),
    dict(id="m5max-s3-peak-int8-d128", run="peak_int8_512x64_d128", variant=None, value=("derived", "TOPS"), nd=1,
         suite="s3_ane_raw", bench="silicon-ledger-bench S3 (ANE raw, private API)",
         command="bench spike && bench ane",
         metric="ANE throughput", unit="TOPS", unit_kind="ops", dtype="int8 W8A16",
         runtime="ANE (_ANEInMemoryModel)", placement="ANE",
         scope="512ch x 128d x 64sp, working set 48 MB, 100 iters"),
    dict(id="m5max-s3-peak-fp16-256x64-d256", run="peak_256x64_d256", variant=None, value=("derived", "TOPS"), nd=1,
         suite="s3_ane_raw", bench="silicon-ledger-bench S3 (ANE raw, private API)",
         command="bench spike && bench ane",
         metric="ANE throughput", unit="TOPS", unit_kind="ops", dtype="fp16",
         runtime="ANE (_ANEInMemoryModel)", placement="ANE",
         scope="256ch x 256d x 64sp, working set 48 MB, 100 iters"),
    dict(id="m5max-s3-scale4096", run="scale_4096", variant=None, value=("median",), nd=1,
         suite="s3_ane_raw", bench="silicon-ledger-bench S3 (ANE raw, private API)",
         command="bench spike && bench ane",
         metric="ANE latency", unit="ms/eval", unit_kind="ms", dtype="fp32 IO",
         runtime="ANE (_ANEInMemoryModel)", placement="ANE",
         scope="4096ch x 1d x 4096sp, working set 96 MB, 100 iters", latency=True),
    # ---- S4 Core AI (official stack) ----
    # ane_regions=0: AOT artifact fact (0 *ANE_region* in every generated bundle for all three
    # graphs, both target boards) — the silent GPU fallback, proven at artifact level.
    dict(id="m5max-s4-coreai-matmul", run="coreai_matmul", variant="default", value=("derived", "TOPS"), nd=1,
         suite="s4_coreai", bench="silicon-ledger-bench S4 (Core AI)", command="make coreai",
         metric="Core AI throughput", unit="TOPS", unit_kind="ops", dtype="fp16",
         runtime="Core AI (.aimodel)", placement="GPU (ANE fallback)", ane_regions=0,
         scope="2048x2048 matmul, torch-validated, median of 50"),
    dict(id="m5max-s4-coreai-deep-fp16", run="coreai_deep_fp16", variant="default", value=("derived", "TOPS"), nd=2,
         suite="s4_coreai", bench="silicon-ledger-bench S4 (Core AI)", command="make coreai",
         metric="Core AI throughput", unit="TOPS", unit_kind="ops", dtype="fp16",
         runtime="Core AI (.aimodel)", placement="GPU (ANE fallback)", ane_regions=0,
         scope="32-layer deep graph, torch-validated, median of 50"),
    dict(id="m5max-s4-coreai-deep-int8", run="coreai_deep_int8", variant="default", value=("derived", "TOPS"), nd=2,
         suite="s4_coreai", bench="silicon-ledger-bench S4 (Core AI)", command="make coreai",
         metric="Core AI throughput", unit="TOPS", unit_kind="ops", dtype="int8",
         runtime="Core AI (.aimodel)", placement="GPU (ANE fallback)", ane_regions=0,
         scope="32-layer deep graph, W8A8 (validation failed: rel_err 5.4e+66), median of 50"),
]


def find_run(report: dict, c: dict) -> dict:
    for s in report["sections"]:
        if s["id"] != c["suite"]:
            continue
        for r in s["runs"]:
            if r["name"] != c["run"]:
                continue
            if c["variant"] is None or r.get("variant") == c["variant"]:
                return r
    raise SystemExit(f"{c['id']}: run {c['run']!r} (variant {c['variant']!r}) not found in {c['suite']}")


def extract(c: dict, run: dict) -> float:
    kind, *rest = c["value"]
    raw = run["derived"][rest[0]] if kind == "derived" else run["median"]
    v = round(raw, c["nd"])
    if c["nd"] == 0 and float(v).is_integer():
        v = int(v)  # whole counts stay integers in the ledger (60750, not 60750.0)
    return v


def build_rows(report: dict, report_path: str) -> list[dict]:
    machine = report.get("machine", {})
    chip = machine.get("chip")
    if chip != EXPECTED_CHIP:
        raise SystemExit(f"report machine is {chip!r}, these claim rows are declared for {EXPECTED_CHIP!r} — refusing")
    fp = machine.get("fingerprint", "?")
    date = report.get("generated", "")[:10]
    rows = []
    for c in CLAIMS:
        run = find_run(report, c)
        value = extract(c, run)
        d = {
            "id": c["id"],
            "model": MODEL,
            "checkpoint": CHECKPOINT,
            "params_m": None,
            "runtime": c["runtime"],
            "placement": c["placement"],
            "dtype": c["dtype"],
            "seq_len": None,
            "ane_regions": c.get("ane_regions"),
            "benchmark": c["bench"],
            "split": None,
            "scope": c["scope"],
            "tiers": None,
            "metric": c["metric"],
            "value": value,
            "unit": c["unit"],
            "latency_ms": value if c.get("latency") else None,
            "latency_unit": f"per eval ({run['iters']} iters, median)" if c.get("latency") else None,
            "hardware": HARDWARE,
            "load_factor": None,
            "energy_mw": None,
            "energy_rail": None,
            "energy_baseline": None,
            "provenance": f"ours (silicon-ledger-bench, {report_path}; fingerprint {fp})",
            "date": date,
            "command": c["command"],
            "unit_kind": c["unit_kind"],
        }
        # machine-check: the stored value must be the report value at the declared rounding
        raw = run["derived"][c["value"][1]] if c["value"][0] == "derived" else run["median"]
        if value != round(raw, c["nd"]):
            raise SystemExit(f"{c['id']}: value {value} != round(report {raw}, {c['nd']})")
        rows.append({k: d[k] for k in FIELDS if k != "protocol"})
    return rows


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("report", help="bench report JSON (silicon-ledger-bench)")
    ap.add_argument("--as", dest="as_path", default=None,
                    help="path recorded in provenance (e.g. the repo-relative path inside "
                         "silicon-ledger-bench); default: path relative to this repo, or the file name")
    ap.add_argument("--apply", action="store_true",
                    help="append claim ids that are not yet in the ledger")
    args = ap.parse_args()

    report_path = Path(args.report).expanduser().resolve()
    report = json.loads(report_path.read_text())
    if args.as_path:
        rel = args.as_path
    else:
        try:
            rel = str(report_path.relative_to(ROOT))
        except ValueError:
            rel = report_path.name  # report lives in the sibling bench repo

    rows = build_rows(report, rel)
    by_id = {r["id"]: r for r in rows}
    if len(by_id) != len(rows):
        raise SystemExit("claim table has duplicate ids")

    cur = json.loads(OUT.read_text())
    existing = {m["id"]: m for m in cur["measurements"]}
    shared = sorted(set(by_id) & set(existing))
    new = [r for r in rows if r["id"] not in existing]
    drift = [(rid, k, existing[rid].get(k), by_id[rid].get(k))
             for rid in shared for k in by_id[rid]
             if existing[rid].get(k) != by_id[rid].get(k)]

    if not args.apply:
        print(f"  report           : {rel} (chip {report['machine']['chip']}, fp {report['machine'].get('fingerprint')})")
        print(f"  existing ledger  : {len(existing)} records — UNTOUCHED (byte-identical)")
        print(f"  claim rows       : {len(rows)} — {len(shared)} already in the ledger, {len(new)} new")
        for rid, k, a, b in drift[:20]:
            print(f"    drift {rid}.{k}: ledger={a!r} claims={b!r} (ledger authoritative, NOT applied)")
        for r in new:
            print(f"    new: {r['id']} = {r['value']} {r['unit']}")
        print("  safety           : --apply appends new ids only; nothing is overwritten or dropped.")
        return 0

    if drift:
        raise SystemExit(f"{len(drift)} drifted fields on {len(set(d[0] for d in drift))} shared ids — "
                         "ledger is authoritative; re-curation needs an explicit decision, not an import")

    merged = [dict(m) for m in cur["measurements"]]
    added = 0
    for r in new:
        merged.append(r)
        added += 1
    cur["measurements"] = merged
    cur.setdefault("_merge_history", []).append({
        "tool": "bench/import_bench_reports.py",
        "added": added,
        "report": rel,
        "at": None,
    })
    OUT.write_text(json.dumps(cur, indent=1))
    print(f"  merged -> {len(merged)} records (+{added} appended, existing order preserved) -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
