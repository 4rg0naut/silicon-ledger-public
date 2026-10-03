#!/usr/bin/env python3
"""Faithful repro: Apple's ACTUAL Attention class, with only RoPE and SDPA stubbed.

The earlier repro (minimal_repro_ane_crash.py) hand-rolled the attention and used
`transpose(-3, -1)` for the key, but Apple's real code uses `transpose(-3, -2)` for the key and
leaves `value` un-transposed. So it was testing a different graph -- which is why all 8 cases
compiled while the real attention crashes coreai-build.

This one imports the real thing:
    coreai_models.models.ios.qwen3.Attention / TransformerBlock / Qwen3Model
and stubs only `apply_rope` and the SDPA module, so everything else is byte-for-byte Apple's.

usage:
    python bench/repro_apple_attention.py
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "repos" / "coreai-kit" / "Examples" / "ChatDemo" / ".build"
       / "checkouts" / "coreai-models" / "python" / "src")
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

COREAI_BUILD = ("/private/var/run/com.apple.security.cryptexd/mnt/"
                "com.apple.MobileAsset.MetalToolchain-v27.1.266.1.vbaqjL/"
                "Metal.xctoolchain/usr/bin/coreai-build")
OUT = ROOT / "work" / "exports" / "apple-attn-repro"


def stub_rope_and_sdpa() -> None:
    """Leave everything else exactly as Apple wrote it.

    NOTE on the namespace, because getting it wrong is invisible: Apple's qwen3.py does
    `from coreai_models.primitives.ios.rope import RoPECache, apply_rope`, so it holds its OWN
    reference to apply_rope. Patching `rope.apply_rope` is a **silent no-op** -- the stub looks
    applied and the result looks like a negative ("not RoPE"), which is exactly the wrong
    conclusion this file first produced. Patch the name in qwen3's namespace.
    """
    import coreai_models.models.ios.qwen3 as qwen3
    import coreai_models.primitives.ios.rope as rope
    qwen3.apply_rope = lambda x, c, s: x                     # the one that matters
    rope.apply_rope = qwen3.apply_rope                       # belt and braces
    from coreai_models.primitives.ios import sdpa as sdpa_mod

    class _Id(nn.Module):
        def __init__(self, *a, **kw):      # Attention passes head_dim=...
            super().__init__()

        def forward(self, q, k, v, m=None):
            return q

    sdpa_mod.SDPA = _Id


class EmbedPlusLayer(nn.Module):
    """The 310 MB embedding table + ONE Apple layer -- no tail. Isolates embedding+layer."""
    def __init__(self, cfg) -> None:
        super().__init__()
        from coreai_models.models.ios.qwen3 import Qwen3Model
        self.embed = nn.Parameter(torch.zeros(cfg.vocab_size, 1, cfg.hidden_size))
        self.m = Qwen3Model(cfg)
        self.m.layers = self.m.layers[:1]
        self.register_buffer("in_step", torch.zeros(1, dtype=torch.int32), persistent=False)

    def forward(self, ids, causal_mask):
        h = self.embed[ids]                                   # (B,S,1,D) -- the huge gather
        rope_cos = torch.zeros(1, 512, 1, 128, dtype=torch.float16)
        rope_sin = torch.zeros(1, 512, 1, 128, dtype=torch.float16)
        return self.m(h, rope_cos, rope_sin, self.in_step, causal_mask, None)


class RawModel(nn.Module):
    """Apple's Qwen3Model (1 layer) with the [x,-x] norms, called with fixed-shape args."""
    def __init__(self, cfg) -> None:
        super().__init__()
        from coreai_models.models.ios.qwen3 import Qwen3Model
        self.m = Qwen3Model(cfg)
        self.m.layers = self.m.layers[:1]
        self.register_buffer("in_step", torch.zeros(1, dtype=torch.int32), persistent=False)

    def forward(self, x, causal_mask):
        rope_cos = torch.zeros(1, 512, 1, 128, dtype=torch.float16)
        rope_sin = torch.zeros(1, 512, 1, 128, dtype=torch.float16)
        return self.m(x, rope_cos, rope_sin, self.in_step, causal_mask, None)


class OneLayer(nn.Module):
    """Apple's TransformerBlock verbatim, wrapped with a fixed-shape forward."""

    def __init__(self, cfg) -> None:
        super().__init__()
        from coreai_models.models.ios.qwen3 import TransformerBlock
        self.block = TransformerBlock(cfg, layer_idx=0)
        self.register_buffer("in_step", torch.zeros(1, dtype=torch.int32), persistent=False)

    def forward(self, x, causal_mask):
        rope_cos = torch.zeros(1, 512, 1, 128, dtype=torch.float16)
        rope_sin = torch.zeros(1, 512, 1, 128, dtype=torch.float16)
        return self.block(x, rope_cos, rope_sin, self.in_step, causal_mask, None)


class JustAttention(nn.Module):
    """Apple's Attention alone (no MLP, no norms) — narrows block vs attention."""

    def __init__(self, cfg) -> None:
        super().__init__()
        from coreai_models.models.ios.qwen3 import Attention
        self.attn = Attention(cfg, layer_idx=0)
        self.register_buffer("in_step", torch.zeros(1, dtype=torch.int32), persistent=False)

    def forward(self, x, causal_mask):
        rope_cos = torch.zeros(1, 512, 1, 128, dtype=torch.float16)
        rope_sin = torch.zeros(1, 512, 1, 128, dtype=torch.float16)
        return self.attn(x, rope_cos, rope_sin, self.in_step, causal_mask, None)


def patch_norms_like_export(model, eps: float) -> int:
    """Same patcher the export uses (imported, not re-implemented)."""
    import importlib.util as iu
    spec = iu.spec_from_file_location("rr_export", ROOT / "bench" / "export_reranker_ane.py")
    mod = iu.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    return mod.patch_norms(model, eps)


def ane_mask(seq_len: int) -> torch.Tensor:
    k = torch.arange(seq_len).unsqueeze(1)
    q = torch.arange(seq_len).unsqueeze(0)
    m = (k > q).to(torch.float16).masked_fill(k > q, -40000.0)
    return m.unsqueeze(0).unsqueeze(2)


def build(cfg, which: str) -> nn.Module:
    from coreai_models.models.ios.qwen3 import Qwen3Model
    if which == "attention":
        m = JustAttention(cfg)
    elif which == "block":
        m = OneLayer(cfg)
    elif which == "block_trick":
        m = OneLayer(cfg)
        patch_norms_like_export(m.block, cfg.rms_norm_eps)
    elif which == "embed_layer":
        m = EmbedPlusLayer(cfg)
        patch_norms_like_export(m.m, cfg.rms_norm_eps)
    elif which == "model_trick":
        m = RawModel(cfg)
        patch_norms_like_export(m.m, cfg.rms_norm_eps)
    for p in m.parameters():
        nn.init.normal_(p, std=0.02)
    return m.half().eval()


def export_one(name: str, module: nn.Module, mask: torch.Tensor) -> Path | None:
    from coreai.runtime import AIModelAssetMetadata
    from coreai_torch import TorchConverter, get_decomp_table

    if isinstance(module, EmbedPlusLayer):
        x = torch.zeros(1, 512, dtype=torch.int64)
        prog = torch.export.export(module, args=(x, mask)).run_decompositions(get_decomp_table())
    else:
        x = torch.randn(1, 512, 1, 1024, dtype=torch.float16)
        prog = torch.export.export(module, args=(x, mask)).run_decompositions(get_decomp_table())
    conv = TorchConverter().add_exported_program(
        exported_program=prog, input_names=["x", "causal_mask"], output_names=["y"])
    spec = importlib.util.spec_from_file_location(
        "coreai_mlir_ops", SRC / "coreai_models" / "export" / "mlir_ops.py")
    mlir_ops = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mlir_ops)
    mlir_ops.register_custom_torch_lowering(conv)
    p = conv.to_coreai()
    p.optimize()
    d = OUT / f"{name}.aimodel"
    if d.exists():
        shutil.rmtree(d)
    d.parent.mkdir(parents=True, exist_ok=True)
    md = AIModelAssetMetadata()
    md.author = "faithful Apple-attention repro"
    md.license = "Apache-2.0"
    md.model_description = f"ANE crash repro: {name}"
    p.save_asset(d, md)
    return d


def compile_one(bundle: Path) -> int:
    out = OUT / f"aot_{bundle.stem}"
    if out.exists():
        shutil.rmtree(out)
    r = subprocess.run([COREAI_BUILD, "compile", str(bundle), "--output", str(out),
                        "--platform", "macOS", "--preferred-compute", "neural-engine",
                        "--architecture", "h16g"], capture_output=True)
    return r.returncode


def main() -> int:
    from transformers import AutoConfig
    cfg = AutoConfig.from_pretrained("Qwen/Qwen3-Reranker-0.6B")
    mask = ane_mask(512)
    stub_rope_and_sdpa()

    print(f"{'case':<26}{'compile':>10}")
    for which in ("attention", "block", "model_trick", "embed_layer"):
        try:
            bundle = export_one(which, build(cfg, which), mask)
        except Exception as exc:  # noqa: BLE001
            print(f"{which:<26}{'EXPORT FAILED':>14}  {type(exc).__name__}: {str(exc)[:40]}")
            continue
        rc = compile_one(bundle)
        print(f"{which:<26}{('SIGSEGV' if rc == 139 else ('ok' if rc == 0 else f'exit {rc}')):>10}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
