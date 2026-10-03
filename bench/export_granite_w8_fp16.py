#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "torch==2.9.0",
#     "coreai-torch==0.4.1",
#     "coreai-core==1.0.0b2",
#     "coreai-opt==0.2.1",
#     "coremltools==9.0",
#     "torchao==0.17.0",
#     "safetensors==0.7.0",
#     "numpy==2.2.6",
#     "scikit-learn",
# ]
#
# [tool.uv]
# index-url       = "https://pypi.org/simple"
# prerelease      = "allow"
# index-strategy  = "unsafe-best-match"
# ///
"""PLACEMENT PROBE — Granite-Embedding-97M with **w8 palettized weights AND fp16 compute**.

Why this combination, and why it is not the zoo's w8 variant:

  * The published w8 bundle palettizes the 48 attention/MLP linears but keeps **all compute
    fp32** ("the 180,000x384 fp32 embedding table and all compute stay fp32"). fp32 compute
    cannot form ANE regions on this chip (Apple: "fp32 falls back to GPU/CPU"), so the shipped
    w8 variant would compile to 0 ANE regions just like the fp32 baseline.
  * The zoo notes a "w8 + fp16-table build (167 MB) passed the same CPU gates but was not
    device-qualified and is not published" — i.e. the combination was never taken further.
  * The ANE wants int8 for compute rate: its array has a double-int8 mode at ~1.4-2x the fp16
    rate, and palettization is natively supported ("Neural Engine supports palettization
    (also known as clustering) natively"). Smaller weights also halve the weight stream.

So: same KMeansPalettizerConfig.presets.w8() as the zoo, same 48 linears, same seed — but the
model is loaded in fp16 instead of fp32. The zoo's script is untouched; its dtype line is the
only difference.

NOT A SHIPPABLE BUNDLE: the palettization changes weights, so the numerical result must be
re-gated. The embedding+retrieval gate is evaluated and REPORTED here, not asserted.

usage: uv run bench/export_granite_w8_fp16.py --seq-len 128
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
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
from export_granite_embedding import inputs_of  # noqa: E402

COREAI_BUILD = (
    "/private/var/run/com.apple.security.cryptexd/mnt/"
    "com.apple.MobileAsset.MetalToolchain-v27.1.266.1.vbaqjL/Metal.xctoolchain/usr/bin/coreai-build"
)
ARCH = "h16g"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seq-len", type=int, default=128, choices=[128, 512])
    ap.add_argument("--bits", type=int, default=8, choices=[4, 6, 8],
                    help="palettization bits: w4/w6 (group_size 16) or w8 (per-tensor)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    from coreai.runtime import AIModelAssetMetadata
    from coreai_opt.common import ExportBackend
    from coreai_opt.palettization import KMeansPalettizer, KMeansPalettizerConfig
    from coreai_torch import TorchConverter, get_decomp_table

    torch.set_num_threads(4)
    torch.set_default_device("cpu")
    torch.manual_seed(0)
    np.random.seed(0)

    source = verify_source()
    fixtures = golden(args.seq_len)
    out_dir = args.out or (ROOT / "work" / "exports" / "granite-embedding-97m" /
                           f"w{args.bits}fp16" / f"s{args.seq_len}")
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)

    print(f"source : {source}")
    print(f"variant: w{args.bits}-palettized weights + fp16 compute, S={args.seq_len}, arch {ARCH}")

    # ---- the one difference from the zoo's w8 script: fp16, not fp32 ----
    model = load_granite(source, args.seq_len, dtype=torch.float16)

    cfg = {4: KMeansPalettizerConfig.presets.w4,
           6: KMeansPalettizerConfig.presets.w6,
           8: KMeansPalettizerConfig.presets.w8}[args.bits]()
    example = inputs_of(fixtures["fixtures"][6])
    t0 = time.perf_counter()
    palettizer = KMeansPalettizer(model, cfg)
    model = palettizer.prepare((example["input_ids"], example["attention_mask"]), num_workers=1)
    model = palettizer.finalize(backend=ExportBackend.CoreAI)
    cluster_s = time.perf_counter() - t0
    print(f"palettized (w8 preset, 48 linears) in {cluster_s:.1f}s")

    # ---- gate (reported, not asserted) ----
    vectors = {}
    with torch.inference_mode():
        for spec in fixtures["fixtures"]:
            vectors[spec["id"]] = model(**inputs_of(spec))[0].float().numpy().tolist()
    gate = gate_vectors(fixtures, vectors)
    print(f"embedding gate: {gate['status']}  min_cosine={gate.get('min_cosine'):.9f}  "
          f"max_abs={gate.get('max_abs'):.2e}")
    flips = sum(r["clear_pair_flips"] for r in gate["retrieval"])
    print(f"retrieval     : {sum(r['top1_match'] for r in gate['retrieval'])}/"
          f"{len(gate['retrieval'])} top-1, {flips} clear pair flips")

    # ---- export ----
    with torch.no_grad():
        exported = torch.export.export(model, args=(), kwargs=example)
        decomposed = exported.run_decompositions(get_decomp_table())
    lut_ops = sum(1 for n in decomposed.graph.nodes
                  if n.op == "call_function" and "coreai.lut_to_dense" in str(n.target))
    print(f"lut_to_dense ops: {lut_ops}")

    program = (TorchConverter()
               .add_exported_program(exported_program=decomposed,
                                     input_names=["input_ids", "attention_mask"],
                                     output_names=["embedding"])
               .to_coreai())
    program.optimize()
    assert program._mlir_module.operation.verify()

    meta = AIModelAssetMetadata()
    meta.author = "w8+fp16 ANE placement probe (not shippable)"
    meta.license = "Apache-2.0"
    meta.model_description = (f"Granite-Embedding-97M w{args.bits}-palettized weights, fp16 compute, "
                              f"S={args.seq_len} — ANE placement probe.")
    bundle = out_dir / f"granite97m_w{args.bits}_fp16_s{args.seq_len}.aimodel"
    program.save_asset(bundle, meta)
    size = sum(f.stat().st_size for f in bundle.rglob("*") if f.is_file())
    print(f"exported: {bundle.name}  {size/1e6:.0f} MB")

    # ---- AOT compile for the ANE ----
    aot = out_dir / "aot"
    aot.mkdir(exist_ok=True)
    argv = [COREAI_BUILD, "compile", str(bundle), "--output", str(aot), "--platform", "macOS",
            "--preferred-compute", "neural-engine", "--architecture", ARCH]
    print(f"$ {' '.join(argv)}")
    t1 = time.perf_counter()
    r = subprocess.run(argv, capture_output=True, text=True)
    compile_s = time.perf_counter() - t1
    if r.returncode != 0:
        print(f"compile FAILED: {r.stderr[-300:]}")
        return 1
    compiled = sorted(aot.glob("*.aimodelc"))
    regions = sum(len(list(c.rglob("*ANE_region*"))) for c in compiled)
    delegates = sorted({p.name for cc in compiled for p in cc.rglob("*")
                        if p.is_dir() and p.parent.name.endswith("-delegates")})
    print(f"\nANE regions : {regions}   delegates: {delegates}   compile {compile_s:.1f}s")

    record = {"variant": f"w{args.bits} weights + fp16 compute", "bits": args.bits,
              "sequence_length": args.seq_len,
              "gate": gate["status"], "min_cosine": gate.get("min_cosine"),
              "max_abs": gate.get("max_abs"), "lut_ops": lut_ops,
              "ane_regions": regions, "delegates": delegates, "bytes": size,
              "bundle": str(compiled[0]) if compiled else None,
              "note": "placement probe; palettization changes weights, not shippable as-is"}
    (out_dir / "probe-record.json").write_text(json.dumps(record, indent=2))
    print(f"record: {out_dir / 'probe-record.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
