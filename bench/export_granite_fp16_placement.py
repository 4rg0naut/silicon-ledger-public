#!/usr/bin/env python3
"""PLACEMENT PROBE — export Granite-Embedding-97M as fp16 and count ANE regions.

NOT A SHIPPABLE BUNDLE. The zoo documents that fp16 fails this checkpoint's *layer* numerics
gate ("fp16 fails the authoring layer gate on this checkpoint; fp32 ships"), which is why fp32
is the published variant. This script deliberately skips that precondition because it asks a
different question: **can this graph reach the Neural Engine at all?**

Why fp16: Apple's Neural Engine authoring rules state
    "Supported dtypes: fp16, int8, int16. fp32 falls back to GPU/CPU."
and the fp32 bundle compiles to 0 ANE regions. A control probe on a trivial ANE-shaped graph
(bench/probe_ane_regions.py) showed fp16 -> 66 regions, fp32 -> 0 on this machine, so dtype is
a necessary condition. This tests whether it is also sufficient for the real graph.

The embedding gate is still evaluated and REPORTED (not asserted): it tells us whether the
fp16 graph is numerically usable even if it does not meet the stricter layer gate.

usage: .venv/bin/python bench/export_granite_fp16_placement.py --seq-len 128
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parent.parent
ZOO = ROOT / "repos" / "coreai-model-zoo"
sys.path.insert(0, str(ZOO / "conversion"))
sys.path.insert(0, str(ZOO / "conversion" / "granite_embedding"))

os.environ.setdefault("ZOO_WORK_ROOT", str(ROOT / "work"))
os.environ.setdefault("ZOO_EXPORTS", str(ROOT / "work" / "exports"))

from _common import golden, verify_source  # noqa: E402
from _gate_metrics import gate_vectors  # noqa: E402
from _granite_model import load_granite  # noqa: E402

COREAI_BUILD = (
    "/private/var/run/com.apple.security.cryptexd/mnt/"
    "com.apple.MobileAsset.MetalToolchain-v27.1.266.1.vbaqjL/Metal.xctoolchain/usr/bin/coreai-build"
)


def inputs_of(spec: dict) -> dict:
    return {"input_ids": torch.tensor([spec["input_ids"]], dtype=torch.int32),
            "attention_mask": torch.tensor([spec["attention_mask"]], dtype=torch.int32)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seq-len", type=int, default=128, choices=[128, 512])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    from coreai.runtime import AIModelAssetMetadata
    from coreai_torch import TorchConverter, get_decomp_table

    torch.set_num_threads(4)
    source = verify_source()
    fixtures = golden(args.seq_len)
    out_dir = args.out or (ROOT / "work" / "exports" / "granite-embedding-97m" /
                           "macos" / f"fp16-s{args.seq_len}-ane")
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)

    print(f"source   : {source}")
    print(f"dtype    : fp16   seq_len: {args.seq_len}")
    print(f"out      : {out_dir}")

    model = load_granite(source, args.seq_len, dtype=torch.float16)

    # ---- torch.export + decomposition, then the embedding gate (REPORTED, not asserted) ----
    t0 = time.perf_counter()
    with torch.no_grad():
        exported = torch.export.export(model, args=(), kwargs=inputs_of(fixtures["fixtures"][6]))
        decomposed = exported.run_decompositions(get_decomp_table())
        candidate = decomposed.module()
        vectors = {r["id"]: candidate(**inputs_of(r))[0].float().numpy().tolist()
                   for r in fixtures["fixtures"]}
    gate = gate_vectors(fixtures, vectors)
    print(f"\nembedding gate (fp16): status={gate['status']}  "
          f"min_cosine={gate.get('min_cosine')}  max_err={gate.get('max_abs_err')}")
    if gate["status"] != "PASS":
        print(f"  failures: {json.dumps(gate.get('failures'), indent=2)[:600]}")
    print(f"  (informational: the zoo's stricter LAYER gate is what rejects fp16)")

    # ---- convert ----
    program = (TorchConverter()
               .add_exported_program(exported_program=decomposed,
                                     input_names=["input_ids", "attention_mask"],
                                     output_names=["embedding"])
               .to_coreai())
    program.optimize()
    module = program._mlir_module
    assert module.operation.verify()

    counts: Counter = Counter()

    def inspect(op) -> None:
        counts[op.name] += 1
        for region in op.regions:
            for block in region.blocks:
                for child in block.operations:
                    inspect(child.operation)

    inspect(module.operation)

    meta = AIModelAssetMetadata()
    meta.author = "PLACEMENT PROBE (not a shippable bundle); weights IBM Granite"
    meta.license = "Apache-2.0"
    meta.model_description = (
        f"Granite-Embedding-97M-R2 fp16 S={args.seq_len} — ANE placement probe. "
        "fp16 fails the zoo's authoring layer gate; this bundle exists only to test "
        "whether the graph can reach the Neural Engine.")
    bundle = out_dir / f"granite97m_fp16_s{args.seq_len}.aimodel"
    program.save_asset(bundle, meta)
    export_seconds = time.perf_counter() - t0
    size = sum(f.stat().st_size for f in bundle.rglob("*") if f.is_file())
    print(f"\nexported : {bundle.name}  {size} bytes  in {export_seconds:.1f}s")

    # ---- AOT compile for the Neural Engine and count regions ----
    aot_dir = out_dir / "aot"
    aot_dir.mkdir(exist_ok=True)
    argv = [COREAI_BUILD, "compile", str(bundle), "--output", str(aot_dir),
            "--platform", "macOS", "--preferred-compute", "neural-engine"]
    print(f"\n$ {' '.join(argv)}")
    t1 = time.perf_counter()
    r = subprocess.run(argv, capture_output=True, text=True)
    compile_seconds = time.perf_counter() - t1
    print(r.stdout[-400:].strip() or r.stderr[-400:].strip())
    if r.returncode != 0:
        print("compile FAILED")
        return 1

    compiled = sorted(aot_dir.glob("*.aimodelc"))
    print(f"\ncompile  : {compile_seconds:.1f}s -> {[c.name for c in compiled]}")
    for c in compiled:
        regions = list(c.rglob("*ANE_region*"))
        delegates = sorted({p.name for p in c.rglob("*")
                            if p.is_dir() and p.parent.name.endswith("-delegates")})
        print(f"\n=== {c.name} ===")
        print(f"  ANE regions : {len(regions)}")
        print(f"  delegates   : {delegates or ['(none)']}")
        if len(regions) > 1:
            print(f"  region files: {[p.name for p in regions[:5]]}")

    record = {
        "status": gate["status"], "min_cosine": gate.get("min_cosine"),
        "max_abs_err": gate.get("max_abs_err"), "dtype": "fp16",
        "sequence_length": args.seq_len, "bundle": str(bundle), "bytes": size,
        "export_seconds": round(export_seconds, 1), "compile_seconds": round(compile_seconds, 1),
        "ane_regions": {c.name: len(list(c.rglob("*ANE_region*"))) for c in compiled},
        "note": "PLACEMENT PROBE: fp16 fails the zoo's authoring layer gate; not shippable.",
    }
    (out_dir / "probe-record.json").write_text(json.dumps(record, indent=2))
    print(f"\nrecord: {out_dir / 'probe-record.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
