#!/usr/bin/env python3
"""ANE residency sweep — which of the graph's f32/GPU-isms keep it off the Neural Engine?

The fp16 export of Granite-Embedding-97M reaches the ANE (14 regions) but stays *segmented*:
MPSGraph delegates are still emitted, so the graph is split across ANE and GPU. Apple's
authoring rules name the culprits:

    "Any Python float literal or fp32 op creates an f32 buffer that Neural Engine cannot
     execute — it falls back to GPU/CPU"

The zoo's graph has three of them, and they are patchable one at a time without touching the
zoo's file (the classes are monkey-patched in memory):

  v0  as-is                                   (fp32 softmax, float literal scale, fp32 pooling)
  v1  + softmax in the graph dtype            (drop `dtype=torch.float32`)
  v2  + scale as an f16 buffer                (drop the `** -0.5` float literal)
  v3  + pooling without the `.float()` cast   (L2 normalize in the graph dtype)

Each variant is exported, gated, compiled for h16g with `--preferred-compute neural-engine`,
and its ANE region count recorded. Regions > 0 means the ANE took it; more regions with fewer
MPSGraph segments means better residency. Runtime benchmarking is a separate step
(bench/bench_ane_variants.sh) because it needs the runner and enginemon.

usage: .venv/bin/python bench/granite_ane_variants.py [--variants v0,v1,v2,v3] [--seq-len 128]
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

import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parent.parent
ZOO = ROOT / "repos" / "coreai-model-zoo"
sys.path.insert(0, str(ZOO / "conversion"))
sys.path.insert(0, str(ZOO / "conversion" / "granite_embedding"))

os.environ.setdefault("ZOO_WORK_ROOT", str(ROOT / "work"))
os.environ.setdefault("ZOO_EXPORTS", str(ROOT / "work" / "exports"))

from _common import golden, verify_source  # noqa: E402
from _gate_metrics import gate_vectors  # noqa: E402
import _granite_model as G  # noqa: E402

COREAI_BUILD = (
    "/private/var/run/com.apple.security.cryptexd/mnt/"
    "com.apple.MobileAsset.MetalToolchain-v27.1.266.1.vbaqjL/Metal.xctoolchain/usr/bin/coreai-build"
)
ARCH = "h16g"  # this machine (M4); `coreai-build inspect` reports it
allow_missing = False

VARIANTS = {
    "v0": "as-is (fp32 softmax, float-literal scale, fp32 pooling)",
    "v1": "+ softmax in graph dtype",
    "v2": "+ scale as f16 buffer",
    "v3": "+ pooling without .float()",
}


def apply_variant(variant: str) -> None:
    """Monkey-patch the zoo's classes in memory. Level = highest digit applied."""
    level = int(variant[1])

    # v1+: softmax in the graph dtype (kills the f32 buffer Apple warns about)
    if level >= 1:
        use_buffer_scale = level >= 2   # constant at trace time; v2 supplies the buffer

        def attn_forward(self, hidden_states, global_mask, local_mask):
            qkv = self.Wqkv(hidden_states).reshape(
                1, self.seq_len, 3, self.num_heads, self.head_dim)
            query, key, value = qkv.transpose(3, 1).unbind(dim=2)
            cosine = self.rope_cos.to(query.dtype)
            sine = self.rope_sin.to(query.dtype)
            query = query * cosine + G._rotate_half(query) * sine
            key = key * cosine + G._rotate_half(key) * sine
            scale = self._scale if use_buffer_scale else (self.head_dim ** -0.5)
            scores = torch.matmul(query, key.transpose(2, 3)) * scale
            scores = scores + (local_mask if self.is_local else global_mask)
            probabilities = F.softmax(scores, dim=-1)          # no dtype=float32
            attended = torch.matmul(probabilities, value)
            attended = attended.transpose(1, 2).contiguous().reshape(
                1, self.seq_len, self.hidden_size)
            return self.Wo(attended)
        G._Attention.forward = attn_forward

    # v2+: scale as an f16 buffer instead of the `head_dim ** -0.5` Python float
    if level >= 2:
        orig_init = G._Attention.__init__

        def attn_init(self, config, seq_len, layer_id, mutation):
            orig_init(self, config, seq_len, layer_id, mutation)
            self.register_buffer("_scale",
                                 torch.tensor(self.head_dim ** -0.5, dtype=torch.float16),
                                 persistent=False)
        G._Attention.__init__ = attn_init

    # v3+: L2 normalize in the graph dtype rather than upcasting to fp32
    if level >= 3:
        def pool(self, hidden_states, attention_mask):
            if self.mutation == "wrong_pooling":
                weights = attention_mask.unsqueeze(-1).to(hidden_states.dtype)
                pooled = (hidden_states * weights).sum(dim=1) / weights.sum(dim=1).clamp_min(1.0)
            else:
                pooled = hidden_states[:, 0]
            return pooled * pooled.square().sum(dim=-1, keepdim=True).clamp_min(1e-24).rsqrt()
        G.GraniteEmbedding._pool = pool


def inputs_of(spec: dict) -> dict:
    return {"input_ids": torch.tensor([spec["input_ids"]], dtype=torch.int32),
            "attention_mask": torch.tensor([spec["attention_mask"]], dtype=torch.int32)}


def run_variant(variant: str, seq_len: int) -> dict:
    from coreai.runtime import AIModelAssetMetadata
    from coreai_torch import TorchConverter, get_decomp_table

    apply_variant(variant)
    source = verify_source()

    # The per-grid fixtures only exist for S=128 and S=512 (they come from the published
    # bundles). For a grid sweep the other values need an example input to trace, and the gate
    # needs per-grid reference embeddings we do not have. Allow a synthetic example and skip the
    # gate -- the graph is identical, only S changes, and correctness is established at 128/512
    # against the HF oracle. `--allow-missing-fixtures` makes that explicit rather than implicit.
    try:
        fixtures = golden(seq_len)
        have_fixtures = True
    except FileNotFoundError:
        if not allow_missing:
            raise
        import numpy as _np
        vocab = 180_000
        rng = _np.random.default_rng(0)
        ids = _np.concatenate([[179934], rng.integers(1000, vocab - 100, size=seq_len - 2), [179938]])
        fixtures = {"fixtures": [{"id": f"synthetic_{i}",
                                  "input_ids": ids.astype(int).tolist(),
                                  "attention_mask": [1] * seq_len,
                                  "kind": "document", "text": ""} for i in range(35)]}
        have_fixtures = False
        print(f"  no fixtures for S={seq_len}: synthetic example input, gate skipped")
    # NOTE: the grid MUST be in the path. Without it every export rmtree's the same directory and
    # only the last grid survives -- which silently destroyed four bundles during a sweep.
    out_dir = (ROOT / "work" / "exports" / "granite-embedding-97m" / "ane-sweep"
               / f"{variant}-s{seq_len}")
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)

    print(f"\n### {variant}: {VARIANTS[variant]}")
    model = G.load_granite(source, seq_len, dtype=torch.float16)

    t0 = time.perf_counter()
    with torch.no_grad():
        exported = torch.export.export(model, args=(), kwargs=inputs_of(fixtures["fixtures"][6]))
        decomposed = exported.run_decompositions(get_decomp_table())
        candidate = decomposed.module()
        vectors = {r["id"]: candidate(**inputs_of(r))[0].float().numpy().tolist()
                   for r in fixtures["fixtures"]}
    if have_fixtures:
        gate = gate_vectors(fixtures, vectors)
        print(f"  embedding gate: {gate['status']}  min_cosine={gate.get('min_cosine'):.9f}")
    else:
        gate = {"status": "SKIPPED", "min_cosine": None}

    program = (TorchConverter()
               .add_exported_program(exported_program=decomposed,
                                     input_names=["input_ids", "attention_mask"],
                                     output_names=["embedding"])
               .to_coreai())
    program.optimize()
    assert program._mlir_module.operation.verify()

    meta = AIModelAssetMetadata()
    meta.author = "ANE residency sweep (probe, not shippable)"
    meta.license = "Apache-2.0"
    meta.model_description = f"Granite-Embedding-97M fp16 S={seq_len} variant {variant}: {VARIANTS[variant]}"
    bundle = out_dir / f"granite97m_fp16_s{seq_len}_{variant}.aimodel"
    program.save_asset(bundle, meta)
    export_s = time.perf_counter() - t0

    aot = out_dir / "aot"
    aot.mkdir(exist_ok=True)
    argv = [COREAI_BUILD, "compile", str(bundle), "--output", str(aot), "--platform", "macOS",
            "--preferred-compute", "neural-engine", "--architecture", ARCH]
    t1 = time.perf_counter()
    r = subprocess.run(argv, capture_output=True, text=True)
    compile_s = time.perf_counter() - t1
    if r.returncode != 0:
        print(f"  compile FAILED: {r.stderr[-200:]}")
        return {"variant": variant, "regions": -1, "gate": gate["status"]}

    compiled = sorted(aot.glob("*.aimodelc"))
    regions = sum(len(list(c.rglob("*ANE_region*"))) for c in compiled)
    delegates = sorted({p.name for cc in compiled for p in cc.rglob("*")
                        if p.is_dir() and p.parent.name.endswith("-delegates")})
    print(f"  ANE regions: {regions}   delegates: {delegates or ['(none)']}"
          f"   compile {compile_s:.1f}s   export {export_s:.1f}s")
    return {"variant": variant, "desc": VARIANTS[variant], "regions": regions,
            "gate": gate["status"], "min_cosine": gate.get("min_cosine"),
            "bundle": str(compiled[0]) if compiled else None,
            "export_seconds": round(export_s, 1), "compile_seconds": round(compile_s, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default="v0,v1,v2,v3")
    ap.add_argument("--seq-len", type=int, default=128)
    ap.add_argument("--allow-missing-fixtures", action="store_true",
                    help="sweep grids without published fixtures: synthetic example, gate skipped")
    args = ap.parse_args()

    global allow_missing
    allow_missing = args.allow_missing_fixtures
    torch.set_num_threads(4)
    results = [run_variant(v.strip(), args.seq_len) for v in args.variants.split(",") if v.strip()]

    print("\n" + "=" * 78)
    print(f"ANE RESIDENCY SWEEP — Granite-Embedding-97M fp16, S={args.seq_len}, arch {ARCH}")
    print("=" * 78)
    print(f"{'variant':<9}{'ANE regions':>13}{'gate':>8}{'min cosine':>16}   change")
    for r in results:
        mc = f"{r.get('min_cosine'):.9f}" if r.get("min_cosine") is not None else "-"
        print(f"{r['variant']:<9}{r['regions']:>13}{r.get('gate',''):>8}{mc:>16}   {r.get('desc','')}")
    out = ROOT / "work" / "exports" / "granite-embedding-97m" / "ane-sweep" / "sweep.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print(f"\nrecord: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
