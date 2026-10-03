#!/usr/bin/env python3
"""Bisection record -- and it is NOT a reproduction. Read this before trusting a case list.

**Outcome: every case below COMPILES.** None of them reproduces the crash. The bug was an
in-graph RoPE gather (`RoPECache.gather_cos_sin`), and every construct in this file omits RoPE
entirely, which is why the sweep came up empty and sent the bisection down the wrong branch for a
while. See EXP-013 for the full story and `export_reranker_ane.py` for the fix.

Kept because it is the record of what was *ruled out* -- that is genuinely useful, since it is why
the answer took so long -- but the filename overclaims and the results must not be read as
evidence about the crash.

Original intent follows.

Minimal reproduction: which construct makes coreai-build SIGSEGV?

Bisection on the full re-authored reranker narrowed it to a single TransformerBlock's attention:
0 layers compiles, 1 layer crashes; stubbing the attention makes it compile again; stubbing RoPE,
SDPA or the MLP does NOT. That leaves the projections and the transpose chain around them.

This exports progressively smaller graphs and AOT-compiles each, to name the exact op. Each step is
a few seconds, so the whole sweep is fast.

usage:
    python bench/minimal_repro_ane_crash.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parent.parent
COREMODELS_SRC = (ROOT / "repos" / "coreai-kit" / "Examples" / "ChatDemo" / ".build"
                  / "checkouts" / "coreai-models" / "python" / "src")
if str(COREMODELS_SRC) not in sys.path:
    sys.path.insert(0, str(COREMODELS_SRC))

COREAI_BUILD = ("/private/var/run/com.apple.security.cryptexd/mnt/"
                "com.apple.MobileAsset.MetalToolchain-v27.1.266.1.vbaqjL/"
                "Metal.xctoolchain/usr/bin/coreai-build")
OUT = ROOT / "work" / "exports" / "minimal-repro"


def bc1s_conv(dim: int) -> nn.Module:
    """Conv2d(1x1) projection, the ANE form of nn.Linear."""
    c = nn.Conv2d(dim, dim, kernel_size=1, bias=False)
    nn.init.normal_(c.weight, std=0.02)
    return c


class JustConv(nn.Module):
    """(B, S, 1, D) -> Conv2d directly (no transpose)."""
    def __init__(self, dim: int) -> None:
        super().__init__()
        self.conv = bc1s_conv(dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, s, _, d = x.shape
        return self.conv(x.reshape(b * s, d, 1, 1)).reshape(b, s, 1, d)


class TransposeConv(nn.Module):
    """The exact pattern Apple's ANE Qwen3 attention uses: transpose(-3,-1) -> Conv2d -> back."""
    def __init__(self, dim: int) -> None:
        super().__init__()
        self.conv = bc1s_conv(dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x.transpose(-3, -1)          # (B,S,1,D) -> (B,D,1,S)   <- a copy on the width dim
        x = self.conv(x)
        return x.transpose(-3, -1)


class TransposeConvReshape(nn.Module):
    """Transpose -> Conv2d -> transpose -> reshape to heads -> transpose back (the real chain)."""
    def __init__(self, dim: int, n_heads: int) -> None:
        super().__init__()
        self.n_heads, self.head_dim = n_heads, dim // n_heads
        self.conv = bc1s_conv(dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, s, _, _ = x.shape
        x = x.transpose(-3, -1)
        q = self.conv(x)
        q = (q.transpose(-3, -1)
             .reshape(b, s, self.n_heads, self.head_dim)
             .transpose(-2, -3))
        q = (q.transpose(-2, -3)
             .reshape(b, s, 1, self.n_heads * self.head_dim)
             .transpose(-3, -1))
        return q


class RMSOnHeads(nn.Module):
    """The [x,-x] LayerNorm trick applied to per-head tensors (q_norm/k_norm)."""
    def __init__(self, dim: int, n_heads: int) -> None:
        super().__init__()
        self.n_heads, self.head_dim = n_heads, dim // n_heads
        self.weight = nn.Parameter(torch.ones(self.head_dim))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, s, _, _ = x.shape
        x = x.transpose(-3, -1)
        q = (x.transpose(-3, -1)
             .reshape(b, s, self.n_heads, self.head_dim)
             .transpose(-2, -3))
        doubled = torch.cat([q, -q], dim=-1)
        n = nn.functional.layer_norm(doubled, (2 * self.head_dim,), weight=None, bias=None, eps=1e-6)
        n, _ = torch.chunk(n, 2, dim=-1)
        q = n * self.weight
        return (q.transpose(-2, -3)
                .reshape(b, s, 1, self.n_heads * self.head_dim)
                .transpose(-3, -1))



class FullAttentionNoRope(nn.Module):
    """A realistic attention block minus RoPE and SDPA -- exactly what the bisection left standing.

    Apple's ANE Qwen3 Attention: transpose -> q/k/v Conv2d -> transpose/reshape/transpose to heads
    -> q_norm/k_norm -> back to BC1S -> o_proj -> transpose. With rope and sdpa stubbed the full
    reranker STILL segfaults, so this is the smallest thing that should reproduce it.
    """
    def __init__(self, dim: int, n_heads: int, n_kv: int) -> None:
        super().__init__()
        self.n_heads, self.n_kv = n_heads, n_kv
        self.head_dim = dim // n_heads
        self.q_proj = bc1s_conv(dim)
        self.k_proj = nn.Conv2d(dim, n_kv * self.head_dim, 1, bias=False)
        self.v_proj = nn.Conv2d(dim, n_kv * self.head_dim, 1, bias=False)
        self.o_proj = bc1s_conv(dim)
        self.q_norm_w = nn.Parameter(torch.ones(self.head_dim))
        self.k_norm_w = nn.Parameter(torch.ones(self.head_dim))

    def _norm(self, x, w):
        d = self.head_dim
        doubled = torch.cat([x, -x], dim=-1)
        n = nn.functional.layer_norm(doubled, (2 * d,), weight=None, bias=None, eps=1e-6)
        n, _ = torch.chunk(n, 2, dim=-1)
        return n * w

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, s, _, d = x.shape
        h, hd = self.n_heads, self.head_dim
        x = x.transpose(-3, -1)
        q = self.q_proj(x)
        k = self.k_proj(x)
        v = self.v_proj(x)
        q = q.transpose(-3, -1).reshape(b, s, h, hd).transpose(-2, -3)
        k = k.transpose(-3, -1).reshape(b, s, self.n_kv, hd).transpose(-2, -3)
        q = self._norm(q, self.q_norm_w)
        k = self._norm(k, self.k_norm_w)
        q = q.transpose(-2, -3).reshape(b, s, 1, h * hd).transpose(-3, -1)
        k = k.transpose(-2, -3).reshape(b, s, 1, self.n_kv * hd).transpose(-3, -1)
        v = v.transpose(-3, -1).reshape(b, s, 1, self.n_kv * hd).transpose(-3, -1)
        out = q + k + v
        out = self.o_proj(out)
        return out.transpose(-3, -1)


class AttnNoNorm(FullAttentionNoRope):
    """Same, with the q/k norms removed -> isolates the norm chains."""
    def __init__(self, dim: int, n_heads: int) -> None:
        super().__init__(dim, n_heads, n_heads)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, s, _, d = x.shape
        h, hd = self.n_heads, self.head_dim
        x = x.transpose(-3, -1)
        q = self.q_proj(x)
        k = self.k_proj(x)
        v = self.v_proj(x)
        q = q.transpose(-3, -1).reshape(b, s, h, hd).transpose(-2, -3)
        q = q.transpose(-2, -3).reshape(b, s, 1, h * hd).transpose(-3, -1)
        k = k.transpose(-3, -1).reshape(b, s, 1, self.n_kv * hd).transpose(-3, -1)
        v = v.transpose(-3, -1).reshape(b, s, 1, self.n_kv * hd).transpose(-3, -1)
        out = self.o_proj(q + k + v)
        return out.transpose(-3, -1)


class AttnNoTranspose(nn.Module):
    """Projections without the transpose dance -> isolates the transpose bookkeeping."""
    def __init__(self, dim: int, n_heads: int) -> None:
        super().__init__()
        self.q_proj = bc1s_conv(dim)
        self.k_proj = bc1s_conv(dim)
        self.v_proj = bc1s_conv(dim)
        self.o_proj = bc1s_conv(dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, s, _, d = x.shape
        flat = x.reshape(b * s, d, 1, 1)
        out = self.q_proj(flat) + self.k_proj(flat) + self.v_proj(flat)
        return self.o_proj(out).reshape(b, s, 1, d)



class RealQwen3Attn(nn.Module):
    """The REAL Qwen3-0.6B attention shape: head_dim 128 while hidden/heads = 64, so q_proj maps
    1024 -> 2048. GQA: 8 kv heads. No rope, no sdpa -- just the projections, the head reshapes and
    the q/k norms, which is all the bisection left standing."""
    def __init__(self, dim: int, n_heads: int, head_dim: int, n_kv: int) -> None:
        super().__init__()
        self.n_heads, self.n_kv, self.head_dim = n_heads, n_kv, head_dim
        self.q_proj = nn.Conv2d(dim, n_heads * head_dim, 1, bias=False)
        self.k_proj = nn.Conv2d(dim, n_kv * head_dim, 1, bias=False)
        self.v_proj = nn.Conv2d(dim, n_kv * head_dim, 1, bias=False)
        self.o_proj = nn.Conv2d(n_heads * head_dim, dim, 1, bias=False)
        self.qw = nn.Parameter(torch.ones(head_dim))
        self.kw = nn.Parameter(torch.ones(head_dim))

    def _norm(self, x, w):
        d = self.head_dim
        doubled = torch.cat([x, -x], dim=-1)
        n = nn.functional.layer_norm(doubled, (2 * d,), weight=None, bias=None, eps=1e-6)
        n, _ = torch.chunk(n, 2, dim=-1)
        return n * w

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, s, _, _ = x.shape
        h, hd, nkv = self.n_heads, self.head_dim, self.n_kv
        x = x.transpose(-3, -1)
        q = self.q_proj(x); k = self.k_proj(x); v = self.v_proj(x)
        q = q.transpose(-3, -1).reshape(b, s, h, hd).transpose(-2, -3)
        k = k.transpose(-3, -1).reshape(b, s, nkv, hd).transpose(-2, -3)
        q = self._norm(q, self.qw)
        k = self._norm(k, self.kw)
        q = q.transpose(-2, -3).reshape(b, s, 1, h * hd).transpose(-3, -1)
        k = k.transpose(-2, -3).reshape(b, s, 1, nkv * hd).transpose(-3, -1)
        v = v.transpose(-3, -1).reshape(b, s, 1, nkv * hd).transpose(-3, -1)
        # widen k/v to the q head count so the widths match for the sum (GQA broadcast)
        k = k.repeat_interleave(h // nkv, dim=1)
        v = v.repeat_interleave(h // nkv, dim=1)
        out = self.o_proj(q + k + v)
        return out.transpose(-3, -1)


CASES = {
    "1_conv_only":            lambda: JustConv(1024),
    "2_transpose_conv":       lambda: TransposeConv(1024),
    "3_transpose_conv_heads": lambda: TransposeConvReshape(1024, 16),
    "4_rms_on_heads":         lambda: RMSOnHeads(1024, 16),
    "5_attn_no_transpose":    lambda: AttnNoTranspose(1024, 16),
    "6_attn_no_norm":         lambda: AttnNoNorm(1024, 16),
    "7_full_attn_no_rope":    lambda: FullAttentionNoRope(1024, 16, 16),
    "8_attn_real_qwen3":      lambda: RealQwen3Attn(1024, 16, 128, 8),
}


def export_one(name: str, module: nn.Module) -> Path | None:
    from coreai.runtime import AIModelAssetMetadata
    from coreai_torch import TorchConverter, get_decomp_table

    module = module.half().eval()
    x = torch.randn(1, 512, 1, 1024, dtype=torch.float16)
    prog = torch.export.export(module, args=(x,)).run_decompositions(get_decomp_table())
    conv = TorchConverter().add_exported_program(
        exported_program=prog, input_names=["x"], output_names=["y"])
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "coreai_mlir_ops", COREMODELS_SRC / "coreai_models" / "export" / "mlir_ops.py")
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
    md.author = "minimal repro"
    md.license = "Apache-2.0"
    md.model_description = f"minimal ANE crash repro: {name}"
    p.save_asset(d, md)
    return d


def compile_one(bundle: Path) -> tuple[int, int]:
    out = OUT / f"aot_{bundle.stem}"
    if out.exists():
        shutil.rmtree(out)
    r = subprocess.run([COREAI_BUILD, "compile", str(bundle), "--output", str(out),
                        "--platform", "macOS", "--preferred-compute", "neural-engine",
                        "--architecture", "h16g"], capture_output=True)
    regions = 0
    for c in out.glob("*.aimodelc"):
        regions += len(list(c.rglob("*ANE_region*")))
    return r.returncode, regions


def main() -> int:
    print(f"{'case':<26}{'export':>10}{'compile':>10}{'ANE regions':>13}")
    for name, make in CASES.items():
        try:
            bundle = export_one(name, make())
        except Exception as exc:  # noqa: BLE001
            print(f"{name:<26}{'FAILED':>10}  {type(exc).__name__}: {str(exc)[:40]}")
            continue
        rc, regions = compile_one(bundle)
        verdict = "SIGSEGV" if rc == 139 else ("ok" if rc == 0 else f"exit {rc}")
        print(f"{name:<26}{'ok':>10}{verdict:>10}{regions:>13}")
    print("\n  139 = SIGSEGV (the coreai-build bug). The first crashing case names the construct.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
