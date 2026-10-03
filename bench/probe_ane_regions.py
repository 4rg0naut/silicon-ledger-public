#!/usr/bin/env python3
"""Does dtype alone decide whether Core AI forms ANE regions on this Mac?

Apple's Neural Engine authoring rules (coreai-models/skills/.../neural_engine_rules.md):

    Supported dtypes: fp16, int8, int16. fp32 falls back to GPU/CPU.

Our Granite encoder is fp32 and compiled to **0 ANE regions** on both macOS and iOS. Before
re-authoring a real model to the ANE recipe (BC1S layout, 1x1 Conv2d, per-head attention),
establish the mechanism on a trivial graph where layout and ops are already ANE-shaped:

    ARM A: the same tiny model in fp16   -> expect ANE regions > 0
    ARM B: the same tiny model in fp32   -> expect ANE regions == 0

If ARM A also gives 0, then fp16 is not the blocker on macOS and re-authoring Granite would
be wasted work. If ARM A > 0 and ARM B == 0, the dtype rule holds on this machine and the
fp16 re-export of the real model is justified.

The model is deliberately ANE-shaped: 1x1 Conv2d (never nn.Linear), BC1S (B, C, 1, S),
LayerNorm over the channel dim, no f32 literals.

usage: .venv/bin/python bench/probe_ane_regions.py
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parent.parent
# Outputs go under work/ (gitignored), never under bench/ — compiled bundles are build
# artifacts and must not be committed. This bit me twice; see FAILURES.md F-18.
OUT = ROOT / "work" / "ane_probe"

COREAI_BUILD = (
    "/private/var/run/com.apple.security.cryptexd/mnt/"
    "com.apple.MobileAsset.MetalToolchain-v27.1.266.1.vbaqjL/Metal.xctoolchain/usr/bin/coreai-build"
)


class TinyANE(nn.Module):
    """1x1 Conv2d + channel LayerNorm on a BC1S tensor — the ANE recipe in miniature."""

    def __init__(self, channels: int = 64, dtype: torch.dtype = torch.float16):
        super().__init__()
        self.conv = nn.Conv2d(channels, channels, kernel_size=1)
        self.norm = nn.LayerNorm(channels)
        self.to(dtype)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = self.conv(x)                        # (B, C, 1, S)
        y = y.squeeze(2).transpose(1, 2)        # -> (B, S, C) for LayerNorm over channels
        y = self.norm(y)
        return y.transpose(1, 2).unsqueeze(2)   # -> (B, C, 1, S)


def export(dtype: torch.dtype, tag: str) -> Path:
    from coreai.runtime import AIModelAssetMetadata
    from coreai_torch import TorchConverter, get_decomp_table

    out = OUT / f"tiny_{tag}.aimodel"
    shutil.rmtree(out, ignore_errors=True)

    model = TinyANE(dtype=dtype).eval()
    x = torch.randn(1, 64, 1, 128, dtype=dtype)

    with torch.no_grad():
        exported = torch.export.export(model, args=(x,))
        decomposed = exported.run_decompositions(get_decomp_table())

    program = (
        TorchConverter()
        .add_exported_program(exported_program=decomposed, input_names=["x"], output_names=["y"])
        .to_coreai()
    )
    program.optimize()
    assert program._mlir_module.operation.verify()

    meta = AIModelAssetMetadata()
    meta.author = "ANE region probe"
    meta.license = "Apache-2.0"
    meta.model_description = f"tiny ANE-shaped probe, {tag}"
    program.save_asset(out, meta)
    print(f"  exported {out.name} ({sum(f.stat().st_size for f in out.rglob('*') if f.is_file())} bytes)")
    return out


def compile_and_count(bundle: Path, tag: str) -> int:
    outdir = OUT / f"aot_{tag}"
    shutil.rmtree(outdir, ignore_errors=True)
    outdir.mkdir(parents=True)
    argv = [COREAI_BUILD, "compile", str(bundle), "--output", str(outdir),
            "--platform", "macOS", "--preferred-compute", "neural-engine"]
    r = subprocess.run(argv, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  compile failed: {r.stdout[-300:]} {r.stderr[-300:]}")
        return -1
    regions = list(outdir.rglob("*ANE_region*"))
    delegates = sorted({p.name for p in outdir.rglob("*") if p.is_dir() and p.parent.name.endswith("-delegates")})
    print(f"  ANE regions: {len(regions)}   delegates: {delegates or ['(none)']}")
    return len(regions)


def main() -> int:
    if not os.path.exists(COREAI_BUILD):
        print(f"coreai-build not found at {COREAI_BUILD}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--dtypes", default="fp16,fp32",
                    help="comma list of fp16,fp32,fp8 (fp8 = torch.float8_e4m3fn)")
    args = ap.parse_args()

    torch_dtypes = {"fp16": torch.float16, "fp32": torch.float32}
    if hasattr(torch, "float8_e4m3fn"):
        torch_dtypes["fp8"] = torch.float8_e4m3fn

    results = {}
    for tag in [t.strip() for t in args.dtypes.split(",") if t.strip()]:
        if tag not in torch_dtypes:
            print(f"\n### ARM {tag}: not supported by this torch build")
            results[tag] = -2
            continue
        print(f"\n### ARM {tag}")
        try:
            bundle = export(torch_dtypes[tag], tag)
            results[tag] = compile_and_count(bundle, tag)
        except Exception as exc:  # noqa: BLE001 - report, do not mask
            print(f"  FAILED: {type(exc).__name__}: {str(exc)[:200]}")
            results[tag] = -3

    print("\n" + "=" * 62)
    print("TINY ANE-SHAPED PROBE, same graph, dtype is the only variable")
    print("=" * 62)
    for tag, n in results.items():
        note = {(-2): "torch lacks this dtype", (-3): "export/compile failed"}.get(n, "")
        print(f"  {tag:<6} ANE regions: {n}   {note}")
    (OUT / "results.json").write_text(json.dumps(results, indent=2))

    print()
    if results.get("fp16", 0) > 0 and results.get("fp32") == 0:
        print("  => dtype decides it. fp16 reaches the ANE; fp32 does not.")
    if "fp8" in results:
        n = results["fp8"]
        if n > 0:
            print(f"  => fp8 forms {n} ANE regions on THIS chip (h16g) - usable here.")
        elif n == 0:
            print("  => fp8 compiles but forms 0 ANE regions on this chip: the fp8 datapath")
            print("     is not present here (the zoo documents it as H18-only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
