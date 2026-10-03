#!/usr/bin/env python3
"""Re-author Qwen3-Reranker-0.6B for the Neural Engine (EXP-013).

The published bundle is a stock **macOS/GPU** export: HF `nn.Linear`, fused SDPA, a
`hidden.gather(...)` for the last token, and an `lm_head` producing a `[B, 151669]` tensor whose
last dimension is not a power of two. Run on the ANE it silently returns 0.5 (FAILURES.md F-32),
because the ANE compiler rejects the graph and nothing says so.

This re-authors it in Apple's ANE dialect, reusing Apple's own verified ANE Qwen3
(`coreai_models.models.ios.qwen3`) rather than hand-rolling 28 layers:

  * activations flow as (B, S, 1, D); each projection transposes to BC1S (B, C, 1, S) for a
    1x1 Conv2d and back -- Apple's `Attention.forward` already does exactly this
  * `nn.Linear` -> `nn.Conv2d(1x1)` with the weight reshaped [O, I] -> [O, I, 1, 1]
  * RMSNorm, gated SiLU MLP, per-head SDPA, Qwen3's q_norm/k_norm, RoPE via RoPECache
  * causal mask -40000.0 (not -inf) in the ANE (1, key, 1, query) layout

Three things are re-authored beyond the stock ANE path, all because a reranker is not an LLM:

  1. **The last-token gather is replaced by mask arithmetic.** Apple flags `gather_nd` as
     producing rank-3 and being rejected; the stock export uses `hidden.gather(1, idx)`. Instead:
     `is_last[t] = m[t] * (1 - m[t+1])` then a weighted sum -- multiply + reduce, no gather.
  2. **The LM head projects to 2 rows, not 151669.** The tied embedding table's rows for
     {no, yes} are selected *before* the matmul, so the head is [D] x [D, 2] instead of
     [D] x [D, 151669]. Mathematically identical; removes the non-power-of-two last dimension
     the alignment rule warns about, and ~76,000x less work.
  3. **No KV cache, no generation.** One forward pass, `cache=None`.

usage:
    python bench/export_reranker_ane.py --seq-len 512 --output-dir work/exports/reranker-ane
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parent.parent
# Apple's coreai-models sources (the ANE Qwen3 + iOS primitives live here)
COREMODELS_SRC = (ROOT / "repos" / "coreai-kit" / "Examples" / "ChatDemo" / ".build"
                  / "checkouts" / "coreai-models" / "python" / "src")
if str(COREMODELS_SRC) not in sys.path:
    sys.path.insert(0, str(COREMODELS_SRC))

from coreai_models.models.ios.qwen3 import Qwen3Model          # noqa: E402
from coreai_models.primitives.ios.rope import RoPECache        # noqa: E402

MODEL_NAME = "Qwen/Qwen3-Reranker-0.6B"
BUNDLE = ROOT / "models" / "qwen3-reranker"
REF = BUNDLE / "reference.json"


def ane_causal_mask(seq_len: int) -> torch.Tensor:
    """Causal mask in the ANE layout (1, key_seq, 1, query_seq), -40000.0 not -inf.

    Neural Engine hardware mishandles IEEE -inf in softmax; -40000.0 is representable in fp16
    and drives exp(-40000) to zero."""
    key_idx = torch.arange(seq_len).unsqueeze(1)
    query_idx = torch.arange(seq_len).unsqueeze(0)
    mask = key_idx > query_idx
    mask = mask.to(torch.float16).masked_fill(mask, -40000.0)
    return mask.unsqueeze(0).unsqueeze(2)


class ANERMSNorm(nn.Module):
    """RMSNorm via the [x, -x] LayerNorm trick -- because the ANE has no RMSNorm and a manual
    `rsqrt(mean(x^2))` overflows in fp16.

    Apple's `RMSNorm` primitive computes `square.mean(-1)` and `rsqrt` in fp16. On the ANE a
    `.float()` cast is a **no-op** -- MPSGraph drops it and the sum-of-squares stays fp16, which
    overflows on large activations. Measured here: the fp32 graph matched HF to 1.19e-07, and the
    SAME graph in fp16 scored 0.877 where HF scores 0.994.

    `LayerNorm([x, -x])` has zero mean by construction, so it equals RMSNorm, and the ANE runs
    LayerNorm with a hardware **fp32-accumulating** kernel -- the actual way to get an fp32
    reduction on the ANE. Recipe per the ANEMLL article ("RMS Norm on the Apple Neural Engine: A
    Simple Hack", 2025-09-16) and the zoo's `gemma4_ane_chunks._Fp32RMSNorm`."""

    def __init__(self, weight: torch.Tensor, eps: float) -> None:
        super().__init__()
        self.weight = nn.Parameter(weight.detach().clone())
        self.eps = eps
        self.dim = weight.numel()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        doubled = torch.cat([x, -x], dim=-1)          # zero-mean -> LayerNorm == RMSNorm
        normed = F.layer_norm(doubled, (2 * self.dim,), weight=None, bias=None, eps=self.eps)
        normed, _ = torch.chunk(normed, 2, dim=-1)    # drop the mirror half
        return normed * self.weight


def patch_norms(model: "Qwen3Model", eps: float) -> int:
    """Swap every composite RMSNorm for the fp32-reduction version. Returns how many were swapped."""
    n = 0
    for layer in model.layers:
        for name in ("input_layernorm", "post_attention_layernorm"):
            old = getattr(layer, name)
            setattr(layer, name, ANERMSNorm(old.weight, eps))
            n += 1
        for name in ("q_norm", "k_norm"):             # Qwen3's per-head QK-norm
            old = getattr(layer.self_attn, name)
            setattr(layer.self_attn, name, ANERMSNorm(old.weight, eps))
            n += 1
    model.norm = ANERMSNorm(model.norm.weight, eps)
    return n + 1


class RerankerANE(nn.Module):
    """Qwen3-Reranker as a single static ANE graph: (input_ids, attention_mask) -> probs[1,2]."""

    def __init__(self, config, no_id: int, yes_id: int, seq_len: int) -> None:
        super().__init__()
        self.seq_len = seq_len
        self.no_id, self.yes_id = no_id, yes_id

        # Embedding table as (V, 1, D) so the lookup lands BC1S-compatible, per Apple's rule.
        self.embed_tokens = nn.Parameter(torch.zeros(config.vocab_size, 1, config.hidden_size))

        self.model = Qwen3Model(config)

        head_dim = getattr(config, "head_dim", config.hidden_size // config.num_attention_heads)
        from coreai_models._hf import resolve_rope_theta
        self.rope = RoPECache(head_dim, seq_len, resolve_rope_theta(config))

        self.register_buffer("position_ids", torch.arange(seq_len).unsqueeze(0), persistent=False)
        self.register_buffer("in_step", torch.zeros(1, dtype=torch.int32), persistent=False)
        # NOTE: the causal mask is deliberately NOT a buffer. A baked 512x512 constant makes the
        # graph materialize + copy a large constant subgraph, and coreai-build SIGSEGVs in
        # MPSGraph's CanonicalizeCopyWithConstraints. The zoo documents the same class of failure
        # (coreai-error-index.md: a degenerate constant-mask subgraph segfaults the pre-compilation
        # rewrite; aot-and-specialization.md: "beta compiler bug, size/shape-correlated"). Apple's
        # own ANE Qwen3 takes causal_mask as a forward ARGUMENT. So do we.
        # The two rows of the (tied) LM head we actually need: {no, yes}, PADDED TO 32 ROWS.
        # Apple's alignment rule: the last dimension must hold >= 32 fp16 (64 B); a [B, 2] output
        # is 4 bytes, and "never use the last axis as a singleton dimension". The extra 30 rows are
        # zero, so the graph output is [B, 32] naturally with no pad/concat op, and relevance is
        # still probs[:, 1]. Filled by load_hf().
        self.head_rows = 32
        self.yn_weight = nn.Parameter(torch.zeros(self.head_rows, config.hidden_size))

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor,
                causal_mask: torch.Tensor, last_token: torch.Tensor,
                rope_cos: torch.Tensor, rope_sin: torch.Tensor) -> torch.Tensor:
        # (B, S) ids -> (B, S, 1, D) embeddings
        hidden = self.embed_tokens[input_ids]                     # (B, S, 1, D)

        # RoPE cos/sin come in as INPUTS, not from an in-graph gather_cos_sin.
        # Apple's rule (knowledge/compute-units-and-authoring.md:39): "RoPE as input: precompute
        # cos/sin outside the graph, pass as 4D (1, head_dim, 1, S) -- in-graph gather_nd makes
        # rank-3 -> ANE rejects." The gather was the ONLY RoPE-related op the graph still contained,
        # and bisection showed RoPE is what segfaults coreai-build.
        hidden = self.model(hidden, rope_cos, rope_sin, self.in_step, causal_mask, None)

        # --- last REAL token: the one-hot comes in as an INPUT ---
        # It used to be computed here as `m * (1 - cat([m[:,1:], zeros_like(m[:,:1])]))`, i.e. a
        # concat against a constant. The zoo's coreai-error-index documents that a degenerate
        # constant-mask subgraph segfaults coreai-build's pre-compilation rewrite, and its fix is
        # "the mask is constant; build it outside the forward" -- which is what this does. The
        # host computes it from the attention mask (it depends on nothing else).
        # hidden is (B, S, 1, D) -> (B, S, D) -> weighted sum over S -> (B, D)
        last_hidden = (hidden.squeeze(2) * last_token.unsqueeze(-1)).sum(dim=1)

        # --- head on 2 rows, not the whole vocab ---
        logits = F.linear(last_hidden, self.yn_weight)            # (B, 32); [:, :2] = [no, yes]
        return F.softmax(logits, dim=-1)

    # ------------------------------------------------------------------ weights
    @torch.no_grad()
    def load_hf(self, hf_model) -> None:
        """Copy HF Qwen3 weights in, reshaping Linear -> Conv2d and picking the {no, yes} rows."""
        sd = {k: v for k, v in hf_model.state_dict().items()}

        self.embed_tokens.copy_(sd["model.embed_tokens.weight"].unsqueeze(1))   # (V,D) -> (V,1,D)

        for i, layer in enumerate(self.model.layers):
            p = f"model.layers.{i}"
            # Linear [O, I] -> Conv2d [O, I, 1, 1]
            for proj in ("q_proj", "k_proj", "v_proj", "o_proj"):
                getattr(layer.self_attn, proj).weight.copy_(
                    sd[f"{p}.self_attn.{proj}.weight"].unsqueeze(-1).unsqueeze(-1))
            for proj in ("gate_proj", "up_proj", "down_proj"):
                getattr(layer.mlp, proj).weight.copy_(
                    sd[f"{p}.mlp.{proj}.weight"].unsqueeze(-1).unsqueeze(-1))
            # norms keep their (D,) weight
            layer.input_layernorm.weight.copy_(sd[f"{p}.input_layernorm.weight"])
            layer.post_attention_layernorm.weight.copy_(sd[f"{p}.post_attention_layernorm.weight"])
            layer.self_attn.q_norm.weight.copy_(sd[f"{p}.self_attn.q_norm.weight"])
            layer.self_attn.k_norm.weight.copy_(sd[f"{p}.self_attn.k_norm.weight"])
        self.model.norm.weight.copy_(sd["model.norm.weight"])

        # tied head: rows [no, yes] of the embedding table
        emb = sd["model.embed_tokens.weight"]
        self.yn_weight.zero_()
        self.yn_weight[0].copy_(emb[self.no_id])      # row 0 = "no"
        self.yn_weight[1].copy_(emb[self.yes_id])     # row 1 = "yes"; rows 2..31 stay zero


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seq-len", type=int, default=512)
    ap.add_argument("--output-dir", type=Path, default=ROOT / "work" / "exports" / "reranker-ane")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--layers", type=int, default=-1,
                    help="truncate the model to N layers (bisecting a compile crash); 0 = all")
    ap.add_argument("--rope-style", choices=["", "flip", "roll"], default="",
                    help="re-author rotate_half without the slice+concat on the width dim")
    ap.add_argument("--bisect", default="",
                    help="bisection: stub out part of the transformer block")
    ap.add_argument("--no-norm-trick", action="store_true",
                    help="keep the composite RMSNorm (bisection: isolates the [x,-x] cat/chunk)")
    ap.add_argument("--gate-only", action="store_true",
                    help="run the numerics gate and exit (no export) — for cross-process checks")
    ap.add_argument("--gate-thresh", type=float, default=1e-2,
                    help="tolerance vs same-precision HF fp16; 28-layer fp16 accumulation gives "
                         "worst |dp| ~6e-3 on borderline pairs; 1e-3 held on M4's shorter pairs")
    ap.add_argument("--skip-gate", action="store_true",
                    help="skip the torch numerics gate (bisection runs only)")
    import contextlib
    _noop = contextlib.nullcontext
    args = ap.parse_args()

    ref = json.loads(REF.read_text())
    no_id, yes_id = ref["no_id"], ref["yes_id"]
    pad_id = ref["pad_token_id"]

    from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer
    print("[INFO] loading HF model (fp32, CPU) ...")
    # fp16, not fp32: this box has 16 GB and the target bundle is fp16 anyway. Loading fp32 and
    # casting later peaks ~6 GB and swaps (measured 2.8 GB of 4 GB swap -> sustained fan).
    ckpt = ROOT / "models" / "qwen3-reranker-hf"
    hf = AutoModelForCausalLM.from_pretrained(ckpt, dtype=torch.float16,
                                              low_cpu_mem_usage=True).eval()
    cfg = hf.config
    tok = AutoTokenizer.from_pretrained(ckpt)

    module = RerankerANE(cfg, no_id, yes_id, args.seq_len)
    module.half()          # in place; copy_ below casts the fp16 HF weights in as it loads
    module.load_hf(hf)
    if args.layers >= 0:
        module.model.layers = module.model.layers[:args.layers]
        cfg.num_hidden_layers = args.layers
        print(f"[INFO] TRUNCATED to {args.layers} layer(s) (bisection)")
    if args.no_norm_trick:
        print("[INFO] KEEPING composite RMSNorm (bisection)")
    else:
        n_swapped = patch_norms(module.model, cfg.rms_norm_eps)
        print(f"[INFO] swapped {n_swapped} composite RMSNorms for the [x,-x] LayerNorm trick")

    if args.bisect == "no-mlp":
        class _Id(nn.Module):
            def forward(self, x): return torch.zeros_like(x)
        for layer in module.model.layers:
            layer.mlp = _Id()
        print("[INFO] BISECT: MLP stubbed to zeros")
    if args.rope_style:
        import coreai_models.models.ios.qwen3 as _q
        import coreai_models.primitives.ios.rope as _r
        if args.rope_style == "flip":
            # No slice, no concat: reshape to (..., d/2, 2), swap the pair, reshape back.
            def _rh(x):
                d = x.shape[-1]
                return x.reshape(*x.shape[:-1], d // 2, 2).flip(-1).reshape(*x.shape[:-1], d)
        else:
            # No slice: a single roll along the width, then a sign flip via a precomputed vector.
            def _rh(x):
                return torch.roll(x, x.shape[-1] // 2, dims=-1)
        _r.rotate_half = _rh
        _q.rotate_half = _rh

        def _apply(x, c, s):
            return (x * c) + (_rh(x) * s)
        _q.apply_rope = _apply
        print(f"[INFO] ROPE re-authored: style={args.rope_style} (no slice+concat)")

    elif args.bisect == "no-rope":
        # NOTE: patch the name in qwen3's namespace, NOT rope's. qwen3.py does
        # `from ...rope import apply_rope`, so it holds its own reference and patching
        # rope.apply_rope is a silent no-op -- which is exactly what happened the first time.
        import coreai_models.models.ios.qwen3 as _q
        _q.apply_rope = lambda x, c, s: x            # identity: no rotate_half slice/concat
        print("[INFO] BISECT: RoPE stubbed to identity (qwen3 namespace)")
    elif args.bisect == "no-sdpa":
        from coreai_models.primitives.ios.sdpa import SDPA as _S
        class _SdpaId(nn.Module):
            def forward(self, q, k, v, m=None): return q
        for layer in module.model.layers:
            layer.self_attn.sdpa = _SdpaId()
        print("[INFO] BISECT: SDPA stubbed to identity")
    elif args.bisect == "no-attn":
        class _IdA(nn.Module):
            def forward(self, x, *a, **k): return torch.zeros_like(x)
        for layer in module.model.layers:
            layer.self_attn = _IdA()
        print("[INFO] BISECT: attention stubbed to zeros")

    module.eval()

    # ---- torch-level gate: does the re-authored graph match HF scoring? ----
    def build(q, d):
        body = f"<Instruct>: {ref['default_instruction']}\n<Query>: {q}\n<Document>: {d}"
        ids = (tok.encode(ref["prefix"], add_special_tokens=False)
               + tok.encode(body, add_special_tokens=False)
               + tok.encode(ref["suffix"], add_special_tokens=False))
        real = len(ids)
        ids = ids + [pad_id] * (args.seq_len - real)
        mask = [1] * real + [0] * (args.seq_len - real)
        return (torch.tensor([ids], dtype=torch.int64), torch.tensor([mask], dtype=torch.int32), real)

    official = ref["official_scores"]
    MASK = ane_causal_mask(args.seq_len)      # fed as a graph INPUT (see RerankerANE.__init__)

    # RoPE cos/sin, computed HERE rather than gathered in-graph (see RerankerANE.forward).
    _head_dim = getattr(cfg, "head_dim", cfg.hidden_size // cfg.num_attention_heads)
    from coreai_models._hf import resolve_rope_theta
    _rope = RoPECache(_head_dim, args.seq_len, resolve_rope_theta(cfg))
    with torch.no_grad():
        ROPE_COS, ROPE_SIN = _rope.gather_cos_sin(torch.arange(args.seq_len).unsqueeze(0))
    ROPE_COS = ROPE_COS.half()
    ROPE_SIN = ROPE_SIN.half()

    def last_token_of(mask_row: torch.Tensor) -> torch.Tensor:
        """(S,) int mask -> (1, S) fp16 one-hot at the last real position. Host-side by design."""
        m = mask_row.to(torch.float16)
        zero = torch.zeros_like(m[:1])
        return (m * (1.0 - torch.cat([m[1:], zero], dim=0))).unsqueeze(0)

    print(f"\n{'pair':<14}{'official':>12}{'HF fp16':>12}{'ANE graph':>12}{'|d|16':>10}{'|d|32':>10}")
    worst, worst16 = 0.0, 0.0
    got_all = {}
    with torch.no_grad() if not args.skip_gate else _noop():
        for name, p in ref["pairs"].items():
            ids, mask, real = build(p["query"], p["doc"])
            got = float(module(ids, mask, MASK, last_token_of(mask[0]), ROPE_COS, ROPE_SIN)[0, 1])
            want = official[name]
            lo = hf(input_ids=ids[:, :real]).logits[0, -1]
            want16 = float(torch.softmax(torch.stack([lo[no_id], lo[yes_id]]), -1)[1])
            d = abs(got - want)
            d16 = abs(got - want16)
            worst = max(worst, d)
            worst16 = max(worst16, d16)
            got_all[name] = got
            print(f"{name:<14}{want:>12.6f}{want16:>12.6f}{got:>12.6f}{d16:>10.2e}{d:>10.2e}")
    print(f"\n  worst |delta| vs HF fp16 (same-precision)  = {worst16:.2e}")
    print(f"  worst |delta| vs HF fp32 (precision cost)  = {worst:.2e}")
    if args.skip_gate:
        print("  (gate skipped — bisection run)")
    elif worst16 >= args.gate_thresh:
        print(f"  FAIL: re-authored graph diverges from same-precision HF (tol {args.gate_thresh:.0e})")
        return 1
    else:
        print(f"  PASS: re-authored graph matches HF fp16 (tol {args.gate_thresh:.0e})")
    if not args.skip_gate:
        for group, members in ref.get("rank_groups", {}).items():
            order = sorted(members, key=lambda m: -got_all[m])
            good = order == members
            print(f"  {'PASS' if good else 'FAIL'}: reauth rank[{group}] {order}")
            if not good:
                return 1

    if args.gate_only:
        print("  (gate-only run; not exporting)")
        return 0

    # The gate is done; the HF model is no longer needed. On a 16 GB box holding fp32 HF +
    # fp32 ANE + torch.export copies at once swaps hard, so drop it before the export.
    del hf
    import gc
    gc.collect()

    # ---- export ----
    from coreai.runtime import AIModelAssetMetadata
    from coreai_torch import TorchConverter, get_decomp_table

    p0 = ref["pairs"].get("rel_capital") or next(iter(ref["pairs"].values()))
    ids0, mask0, _ = build(p0["query"], p0["doc"])
    print("\n[INFO] torch.export ...")
    exported = torch.export.export(module, args=(), kwargs={
        "input_ids": ids0, "attention_mask": mask0, "causal_mask": MASK,
        "last_token": last_token_of(mask0[0]),
        "rope_cos": ROPE_COS, "rope_sin": ROPE_SIN})
    exported = exported.run_decompositions(get_decomp_table())

    print("[INFO] converting to Core AI ...")
    conv = TorchConverter().add_exported_program(
        exported_program=exported,
        input_names=["input_ids", "attention_mask", "causal_mask", "last_token",
                     "rope_cos", "rope_sin"],
        output_names=["probs"],
    )
    # The iOS export path registers these before converting (export/ios.py:121); without it the
    # RoPE custom op has no lowering and to_coreai() dies with
    #   KeyError: 'rope_gather_cached_cos_sin'
    # RoPECache.gather_cos_sin emits coreai::rope_gather_cached_cos_sin, which needs
    # mlir_ops.custom_lowering_rope_gather_cached_cos_sin registered on the converter.
    # Load mlir_ops BY FILE PATH, not `from coreai_models.export.mlir_ops import ...`:
    # the package __init__ pulls in export.pipeline -> export.compression -> `datasets`, which is
    # not installed here. mlir_ops itself only needs coreai/_torch, so a direct spec load works.
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "coreai_mlir_ops", COREMODELS_SRC / "coreai_models" / "export" / "mlir_ops.py")
    _mlir_ops = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mlir_ops)
    _mlir_ops.register_custom_torch_lowering(conv)
    prog = conv.to_coreai()
    prog.optimize()

    out_dir = args.output_dir
    model_path = out_dir / f"qwen3-reranker-0.6b_float16_s{args.seq_len}_ane.aimodel"
    if model_path.exists():
        if not args.overwrite:
            print(f"  {model_path} exists; pass --overwrite")
            return 2
        shutil.rmtree(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    md = AIModelAssetMetadata()
    md.author = "Alibaba Qwen (re-authored for the ANE)"
    md.license = "Apache-2.0"
    md.model_description = (
        "Qwen3-Reranker-0.6B re-authored for the Neural Engine: Conv2d 1x1 projections, BC1S, "
        "per-head SDPA, mask-arithmetic last-token select, 2-row head. Source: "
        "https://huggingface.co/Qwen/Qwen3-Reranker-0.6B")
    md.creation_date = int(time.time())
    prog.save_asset(model_path, md)
    print(f"[INFO] saved {model_path}")
    print(f"[DONE] now AOT-compile it and count ANE regions (0 = silent fallback = FAIL)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
