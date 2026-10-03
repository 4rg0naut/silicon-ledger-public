#!/usr/bin/env python3
"""Laya-multilingual (mmBERT-base + typed decision head) as a static graph for the Neural Engine.

The existing Laya ANE port (`aac6fef/laya-multilingual-coreml-ane`) is **Core ML**. This is the same
model on **Core AI** — the newer Apple runtime — which is the "same idea, different layer" move that
this session's other ports turned out to be.

Graph (from `NayaKishorM/laya` `laya/common.py::DecisionModel.forward`, reproduced faithfully):

    input_ids [1,S] + attention_mask [1,S] + selection [K,S] + qtype scalar
      -> mmBERT-base encoder (22 layers, ModernBERT)
      -> + type_emb(qtype)
      -> 2 pre-norm transformer head layers
      -> m = selection @ h                    <- replaces torch.gather (the ANE blocker)
      -> scorer: LayerNorm -> Linear(768,768) -> GELU -> Linear(768,1)
      -> option logits [K], padded to 32

**The one structural change is the gather.** `DecisionModel.forward` does
`torch.gather(h, 1, marker_pos)`, a data-dependent index op — which Apple's rules reject
("in-graph gather_nd makes rank-3 -> ANE rejects"). It is replaced by a matmul against a
host-built one-hot selection matrix, which is exactly equivalent and fully ANE-legal. The same
substitution fixed the reranker's last-token select (EXP-013).

usage:
    python bench/export_laya_ane.py --seq-len 256 --variant v1 --output-dir work/exports/laya-ane
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
COREMODELS_SRC = (ROOT / "repos" / "coreai-kit" / "Examples" / "ChatDemo" / ".build"
                  / "checkouts" / "coreai-models" / "python" / "src")
MODEL_DIR = ROOT / "models" / "laya-multilingual"
K_SLOTS = 32          # option slots, fixed for a static graph
PAD_TO = 32           # output width for the 64-byte alignment rule

VARIANTS = {
    "v0": "as-is (fp32 softmax, float-literal scale)",
    "v1": "+ softmax in the graph dtype (drop dtype=torch.float32)",
    "v2": "+ scale as an f16 buffer",
}
V = {"softmax_f32": True, "float_scale": True}


def _set_variant(name: str) -> None:
    V["softmax_f32"] = name == "v0"
    V["float_scale"] = name in ("v0", "v1")


def _rotate_half(x: torch.Tensor) -> torch.Tensor:
    x1, x2 = x.chunk(2, dim=-1)
    return torch.cat((-x2, x1), dim=-1)


class Attention(nn.Module):
    """ModernBERT attention (fused Wqkv, RoPE from buffers, explicit matmul, no SDPA)."""

    def __init__(self, cfg: dict, seq_len: int, layer_id: int) -> None:
        super().__init__()
        self.hidden_size = cfg["hidden_size"]
        self.num_heads = cfg["num_attention_heads"]
        self.head_dim = self.hidden_size // self.num_heads
        self.seq_len = seq_len
        self.Wqkv = nn.Linear(self.hidden_size, 3 * self.hidden_size, bias=False)
        self.Wo = nn.Linear(self.hidden_size, self.hidden_size, bias=False)
        types = cfg.get("layer_types")
        self.is_local = (types[layer_id] != "full_attention") if types else \
            (layer_id % cfg["global_attn_every_n_layers"] != 0)
        # Each attention pattern has its OWN rope parameters. This config sets rope_theta=160000
        # for BOTH full_attention and sliding_attention -- hardcoding 10000.0 for the sliding
        # layers (as this did) diverged from HF by 3.06 units at layer 1 alone, compounding to
        # 28.6 by layer 21. Read the theta for the layer's actual type.
        ltype = types[layer_id] if types else ("full_attention" if not self.is_local
                                               else "sliding_attention")
        rp = cfg.get("rope_parameters", {}).get(ltype, {})
        theta = float(rp.get("rope_theta") or cfg.get("rope_theta") or 160000.0)
        inv = 1.0 / (theta ** (torch.arange(0, self.head_dim, 2, dtype=torch.int64).float()
                               / self.head_dim))
        pos = torch.arange(seq_len).unsqueeze(0)
        freqs = (inv[None, :, None] @ pos[:, None, :].float()).transpose(1, 2)
        angles = torch.cat((freqs, freqs), dim=-1).unsqueeze(1)
        self.register_buffer("rope_cos", angles.cos(), persistent=False)
        self.register_buffer("rope_sin", angles.sin(), persistent=False)
        self.register_buffer("_scale", torch.tensor(self.head_dim ** -0.5,
                                                    dtype=torch.float16), persistent=False)

    def forward(self, x, gm, lm):
        qkv = self.Wqkv(x).reshape(1, self.seq_len, 3, self.num_heads, self.head_dim)
        q, k, v = qkv.transpose(3, 1).unbind(dim=2)
        cos, sin = self.rope_cos.to(q.dtype), self.rope_sin.to(q.dtype)
        q = q * cos + _rotate_half(q) * sin
        k = k * cos + _rotate_half(k) * sin
        scale = (self.head_dim ** -0.5) if V["float_scale"] else self._scale.to(q.dtype)
        scores = torch.matmul(q, k.transpose(2, 3)) * scale
        scores = scores + (lm if self.is_local else gm)
        probs = (F.softmax(scores, dim=-1, dtype=torch.float32).to(q.dtype)
                 if V["softmax_f32"] else F.softmax(scores, dim=-1))
        out = torch.matmul(probs, v).transpose(1, 2).contiguous().reshape(1, self.seq_len, -1)
        return self.Wo(out)


class MLP(nn.Module):
    def __init__(self, dim: int, hidden: int, act: str = "gelu") -> None:
        super().__init__()
        self.Wi = nn.Linear(dim, 2 * hidden, bias=False)
        self.Wo = nn.Linear(hidden, dim, bias=False)
        self.act = act

    def forward(self, x):
        inputs, gate = self.Wi(x).chunk(2, dim=-1)
        h = F.gelu(inputs) if self.act == "gelu" else F.silu(inputs)
        return self.Wo(h * gate)


def ln(dim: int, eps: float = 1e-5, bias: bool = False) -> nn.LayerNorm:
    return nn.LayerNorm(dim, eps=eps, elementwise_affine=True, bias=bias)


class EncoderLayer(nn.Module):
    def __init__(self, cfg: dict, seq_len: int, layer_id: int) -> None:
        super().__init__()
        # mmBERT alternates attention patterns. `layer_types` is the authoritative per-layer
        # schedule (8 full + 14 sliding here). Applying one global mask to all 22 layers cost
        # 5.13e-01 on the logits -- the sliding layers must see a local window instead.
        types = cfg.get("layer_types") or []
        if types:
            self.is_sliding = types[layer_id] == "sliding_attention"
        else:
            every = cfg.get("global_attn_every_n_layers") or 0
            self.is_sliding = bool(every) and (layer_id + 1) % every != 0
        self.attn_norm = nn.Identity() if layer_id == 0 else ln(cfg["hidden_size"])
        self.attn = Attention(cfg, seq_len, layer_id)
        self.mlp_norm = ln(cfg["hidden_size"])
        self.mlp = MLP(cfg["hidden_size"], cfg["intermediate_size"], "gelu")

    def forward(self, x, gm, lm):
        # sliding layers get the local band mask; full layers get the global one
        x = x + self.attn(self.attn_norm(x), lm if self.is_sliding else gm, lm)
        return x + self.mlp(self.mlp_norm(x))


class HeadLayer(nn.Module):
    """One `nn.TransformerEncoderLayer(d, nhead, 4d, dropout, batch_first, norm_first=True)`.

    Laya's head uses the stock PyTorch layer, whose parameter names are
    `self_attn.in_proj_weight/out_proj`, `linear1/linear2`, `norm1/norm2` -- so this is
    re-authored with those exact names and the same pre-norm topology.
    """

    def __init__(self, d: int, nhead: int, ffn: int) -> None:
        super().__init__()
        self.nhead = nhead
        self.head_dim = d // nhead
        self.norm1 = ln(d, bias=True)
        self.self_attn_in_proj_weight = nn.Parameter(torch.zeros(3 * d, d))
        self.self_attn_in_proj_bias = nn.Parameter(torch.zeros(3 * d))
        self.self_attn_out_proj_weight = nn.Parameter(torch.zeros(d, d))
        self.self_attn_out_proj_bias = nn.Parameter(torch.zeros(d))
        self.norm2 = ln(d, bias=True)
        self.linear1_weight = nn.Parameter(torch.zeros(ffn, d))
        self.linear1_bias = nn.Parameter(torch.zeros(ffn))
        self.linear2_weight = nn.Parameter(torch.zeros(d, ffn))
        self.linear2_bias = nn.Parameter(torch.zeros(d))

    def forward(self, x, gm, lm):
        # --- pre-norm self-attention ---
        r = x
        h = self.norm1(x)
        qkv = F.linear(h, self.self_attn_in_proj_weight, self.self_attn_in_proj_bias)
        q, k, v = qkv.chunk(3, dim=-1)
        S = x.shape[1]
        q = q.reshape(1, S, self.nhead, self.head_dim).transpose(1, 2)
        k = k.reshape(1, S, self.nhead, self.head_dim).transpose(1, 2)
        v = v.reshape(1, S, self.nhead, self.head_dim).transpose(1, 2)
        scores = torch.matmul(q, k.transpose(2, 3)) * (self.head_dim ** -0.5) + gm
        probs = (F.softmax(scores, dim=-1, dtype=torch.float32).to(q.dtype)
                 if V["softmax_f32"] else F.softmax(scores, dim=-1))
        att = torch.matmul(probs, v).transpose(1, 2).reshape(1, S, -1)
        x = r + F.linear(att, self.self_attn_out_proj_weight, self.self_attn_out_proj_bias)
        # --- pre-norm FFN ---
        r = x
        h = self.norm2(x)
        # PyTorch's nn.TransformerEncoderLayer defaults activation=F.relu, and Laya constructs it
        # WITHOUT overriding that -- so the head's FFN is ReLU, not GELU. Using gelu here cost
        # 10.9 units against the reference layer. Verified against nn.TransformerEncoderLayer
        # directly rather than assumed.
        h = F.relu(F.linear(h, self.linear1_weight, self.linear1_bias))
        return r + F.linear(h, self.linear2_weight, self.linear2_bias)


class LayaANE(nn.Module):
    def __init__(self, cfg: dict, head_cfg: dict, seq_len: int) -> None:
        super().__init__()
        self.seq_len = seq_len
        d = cfg["hidden_size"]
        self.tok_embeddings = nn.Embedding(cfg["vocab_size"], d)
        self.emb_norm = ln(d, eps=cfg.get("norm_eps", 1e-5))
        self.layers = nn.ModuleList(
            [EncoderLayer(cfg, seq_len, i) for i in range(cfg["num_hidden_layers"])])
        self.final_norm = ln(d, eps=cfg.get("norm_eps", 1e-5))
        self.type_emb = nn.Embedding(3, d)
        nhead = max(1, d // 64)
        self.head_layers = nn.ModuleList(
            [HeadLayer(d, nhead, 4 * d) for _ in range(int(head_cfg.get("head_layers", 2)))])
        # scorer: LayerNorm -> Linear(d,d) -> GELU -> Linear(d,1)
        self.scorer_0 = ln(d, bias=True)
        self.scorer_1_weight = nn.Parameter(torch.zeros(d, d))
        self.scorer_1_bias = nn.Parameter(torch.zeros(d))
        self.scorer_3_weight = nn.Parameter(torch.zeros(1, d))
        self.scorer_3_bias = nn.Parameter(torch.zeros(1))
        pos = torch.arange(seq_len)
        dist = (pos[:, None] - pos[None, :]).abs()
        # HF's sliding_window_bidirectional_overlay: abs(q_idx - kv_idx) <= config.sliding_window,
        # ANDed with the padding mask. config.sliding_window == local_attention // 2.
        win = cfg.get("sliding_window")
        if win is None:
            win = cfg["local_attention"] // 2
        self.register_buffer("local_allowed", (dist <= win)[None, None], persistent=False)

    def _masks(self, attention_mask):
        dtype = self.tok_embeddings.weight.dtype
        minimum = torch.finfo(dtype).min
        m = attention_mask[:, None, None, :].to(dtype).expand(1, 1, self.seq_len, self.seq_len)
        inv = 1.0 - m
        gm = inv.masked_fill(inv.to(torch.bool), minimum)
        lm = gm.masked_fill(~self.local_allowed, minimum)
        return gm, lm

    def forward(self, input_ids, attention_mask, selection, qtype):
        gm, lm = self._masks(attention_mask)
        x = self.emb_norm(self.tok_embeddings(input_ids))
        for layer in self.layers:
            x = layer(x, gm, lm)
        x = self.final_norm(x)
        x = x + self.type_emb(qtype).reshape(1, 1, -1)
        for layer in self.head_layers:
            x = layer(x, gm, lm)
        # --- the gather, replaced by a matmul ---
        # DecisionModel does torch.gather(h, 1, marker_pos). A host-built one-hot selection
        # matrix makes this a matmul: (1,K,S) @ (1,S,D) -> (1,K,D). Exactly equivalent.
        m = torch.matmul(selection, x)                       # (1, K, D)
        h = F.gelu(F.linear(self.scorer_0(m), self.scorer_1_weight, self.scorer_1_bias))
        logits = F.linear(h, self.scorer_3_weight, self.scorer_3_bias).reshape(K_SLOTS)
        return F.pad(logits, (0, PAD_TO - K_SLOTS))

    # ---------------------------------------------------------------- weights
    @torch.no_grad()
    def load_hf(self, sd: dict) -> None:
        self.tok_embeddings.weight.copy_(sd["encoder.embeddings.tok_embeddings.weight"])
        self.emb_norm.weight.copy_(sd["encoder.embeddings.norm.weight"])
        for i, layer in enumerate(self.layers):
            p = f"encoder.layers.{i}"
            layer.attn.Wqkv.weight.copy_(sd[f"{p}.attn.Wqkv.weight"])
            layer.attn.Wo.weight.copy_(sd[f"{p}.attn.Wo.weight"])
            layer.mlp.Wi.weight.copy_(sd[f"{p}.mlp.Wi.weight"])
            layer.mlp.Wo.weight.copy_(sd[f"{p}.mlp.Wo.weight"])
            layer.mlp_norm.weight.copy_(sd[f"{p}.mlp_norm.weight"])
            if i > 0:
                layer.attn_norm.weight.copy_(sd[f"{p}.attn_norm.weight"])
        self.final_norm.weight.copy_(sd["encoder.final_norm.weight"])
        self.type_emb.weight.copy_(sd["type_emb.weight"])
        for i, hl in enumerate(self.head_layers):
            p = f"head.layers.{i}"
            hl.norm1.weight.copy_(sd[f"{p}.norm1.weight"]); hl.norm1.bias.copy_(sd[f"{p}.norm1.bias"])
            hl.norm2.weight.copy_(sd[f"{p}.norm2.weight"]); hl.norm2.bias.copy_(sd[f"{p}.norm2.bias"])
            hl.self_attn_in_proj_weight.copy_(sd[f"{p}.self_attn.in_proj_weight"])
            hl.self_attn_in_proj_bias.copy_(sd[f"{p}.self_attn.in_proj_bias"])
            hl.self_attn_out_proj_weight.copy_(sd[f"{p}.self_attn.out_proj.weight"])
            hl.self_attn_out_proj_bias.copy_(sd[f"{p}.self_attn.out_proj.bias"])
            hl.linear1_weight.copy_(sd[f"{p}.linear1.weight"]); hl.linear1_bias.copy_(sd[f"{p}.linear1.bias"])
            hl.linear2_weight.copy_(sd[f"{p}.linear2.weight"]); hl.linear2_bias.copy_(sd[f"{p}.linear2.bias"])
        self.scorer_0.weight.copy_(sd["scorer.0.weight"]); self.scorer_0.bias.copy_(sd["scorer.0.bias"])
        self.scorer_1_weight.copy_(sd["scorer.1.weight"]); self.scorer_1_bias.copy_(sd["scorer.1.bias"])
        self.scorer_3_weight.copy_(sd["scorer.3.weight"]); self.scorer_3_bias.copy_(sd["scorer.3.bias"])


def build_case(tok, cfg, state: str, opts: list, seq_len: int, qtype: int = 2):
    """Pack one decision case exactly as Laya's `build_sequence` does.

    Marker layout: [CLS] then for each option `[MASK] <option tokens>`; the option's marker is the
    MASK position. State follows after [SEP]. Returns the four model inputs.
    """
    ids = [tok.cls_token_id]
    opt_ids = [tok(" " + o, add_special_tokens=False)["input_ids"][:48] for o in opts]
    for o in opt_ids:
        ids += [tok.mask_token_id] + o
    ids += [tok.sep_token_id] + tok(state, add_special_tokens=False)["input_ids"]
    ids = ids[:seq_len]
    real = len(ids)
    sel = torch.zeros(1, K_SLOTS, seq_len)
    cur = 1
    for j, o in enumerate(opt_ids):
        if cur < seq_len:
            sel[0, j, cur] = 1.0
        cur += 1 + len(o)
    iid = torch.tensor([ids + [cfg.get("pad_token_id", 0)] * (seq_len - real)])
    am = torch.tensor([[1] * real + [0] * (seq_len - real)])
    return iid, am, sel, torch.tensor([qtype])      # qtype 2 = "noul" by default


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seq-len", type=int, default=256)
    ap.add_argument("--variant", choices=list(VARIANTS), default="v1")
    ap.add_argument("--output-dir", type=Path, default=ROOT / "work" / "exports" / "laya-ane")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--model-dir", type=Path, default=None,
                    help="checkpoint dir; defaults to models/laya-multilingual")
    args = ap.parse_args()
    global MODEL_DIR
    if args.model_dir is not None:
        MODEL_DIR = args.model_dir
    _set_variant(args.variant)
    print(f"[INFO] variant {args.variant}: {VARIANTS[args.variant]}")

    md = MODEL_DIR
    cfg = json.loads((md / "encoder" / "config.json").read_text())
    head_cfg = json.loads((md / "rl_agent_config.json").read_text())
    from safetensors.torch import load_file
    sd = load_file(str(md / "model.safetensors"))

    module = LayaANE(cfg, head_cfg, args.seq_len)
    module.load_hf(sd)
    module.eval()

    # ---- torch gate: compare against the reference forward, written from common.py ----
    import numpy as np
    from transformers import AutoConfig, AutoModel, AutoTokenizer
    # encoder/ ships only a config; the weights are the `encoder.*`-prefixed tensors in the
    # top-level model.safetensors, so build from config and load those.
    ecfg = AutoConfig.from_pretrained(md / "encoder")
    enc = AutoModel.from_config(ecfg, dtype=torch.float32).eval()
    enc.load_state_dict({k[len("encoder."):]: v.float() for k, v in sd.items()
                         if k.startswith("encoder.")}, strict=False)
    tok = AutoTokenizer.from_pretrained(md / "tokenizer")

    def reference(input_ids, attention_mask, selection, qtype):
        with torch.no_grad():
            h = enc(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
            h = h + module.type_emb(qtype).reshape(1, 1, -1)
            pad = ~attention_mask.bool()
            nhead = max(1, cfg["hidden_size"] // 64)
            ref_head = nn.TransformerEncoder(
                nn.TransformerEncoderLayer(cfg["hidden_size"], nhead, 4 * cfg["hidden_size"],
                                           0.0, batch_first=True, norm_first=True),
                int(head_cfg.get("head_layers", 2)), enable_nested_tensor=False).eval()
            # head.layers.N.<name> -> layers.N.<name>. Strip ONLY "head." -- the reference
            # TransformerEncoder keeps the "layers.N." prefix. Stripping further silently left
            # all 24 head parameters at their random init and cost 12.7 logits, hidden by
            # strict=False. Assert instead.
            hsd = {k.replace("head.", "", 1): v
                   for k, v in sd.items() if k.startswith("head.layers.")}
            missing, unexpected = ref_head.load_state_dict(hsd, strict=False)
            if missing or unexpected:
                raise SystemExit(f"reference head load mismatch: missing={missing} "
                                 f"unexpected={unexpected}")
            for layer in ref_head.layers:
                h = layer(h, src_key_padding_mask=pad)
            m = torch.matmul(selection, h)
            x = F.gelu(F.linear(F.layer_norm(m, (cfg["hidden_size"],),
                                             module.scorer_0.weight, module.scorer_0.bias),
                                module.scorer_1_weight, module.scorer_1_bias))
            return F.linear(x, module.scorer_3_weight, module.scorer_3_bias).reshape(-1)

    CASES = [
        ("refund", "The customer asks for a refund of a duplicate payment.",
         "Does the customer request a refund?", ["refund", "not a refund"]),
        ("billing", "Our card was charged twice for the same invoice this month.",
         "Which department should handle this?", ["billing", "tech", "sales"]),
    ]
    print(f"\n{'case':<12}{'ref argmax':>12}{'ours argmax':>13}{'max|dlogit|':>13}")
    worst = 0.0
    for name, state, ins, opts in CASES:
        iid, am, sel, qt = build_case(tok, cfg, state, opts, args.seq_len)
        ref = reference(iid, am, sel, qt)
        got = module(iid, am, sel, qt)[: len(opts)]
        dl = float((ref[: len(opts)] - got).abs().max())
        worst = max(worst, dl)
        print(f"{name:<12}{int(ref[:len(opts)].argmax()):>12}{int(got.argmax()):>13}{dl:>13.2e}")
    print(f"\n  worst |dlogit| = {worst:.2e}   {'PASS' if worst < 1e-2 else 'FAIL'}")
    if worst >= 1e-2:
        return 1

    # ---- export ----
    from coreai.runtime import AIModelAssetMetadata
    from coreai_torch import TorchConverter, get_decomp_table
    module = module.half()
    iid = iid.to(torch.int32); am = am.to(torch.int32); sel = sel.half(); qt = qt
    print("\n[INFO] torch.export ...")
    exported = torch.export.export(module, args=(iid, am, sel, qt))
    exported = exported.run_decompositions(get_decomp_table())
    conv = TorchConverter().add_exported_program(
        exported_program=exported, input_names=["input_ids", "attention_mask", "selection", "qtype"],
        output_names=["logits"])
    if str(COREMODELS_SRC) not in sys.path:
        sys.path.insert(0, str(COREMODELS_SRC))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "coreai_mlir_ops", COREMODELS_SRC / "coreai_models" / "export" / "mlir_ops.py")
    mlir_ops = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mlir_ops)
    mlir_ops.register_custom_torch_lowering(conv)
    prog = conv.to_coreai()
    prog.optimize()

    out_dir = args.output_dir
    model_path = out_dir / f"laya-multilingual_{args.variant}_float16_s{args.seq_len}_ane.aimodel"
    if model_path.exists():
        if not args.overwrite:
            print(f"  exists; pass --overwrite"); return 2
        shutil.rmtree(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    md = AIModelAssetMetadata()
    md.author = "Convai Innovations (Laya), re-authored for the ANE"
    md.license = "Apache-2.0"
    md.model_description = (
        "Laya-multilingual typed decision model (mmBERT-base + 2-layer decision head), re-authored "
        "for the Neural Engine: the option-marker gather replaced by a selection matmul. Source: "
        "https://github.com/NandhaKishorM/laya")
    md.creation_date = int(time.time())
    prog.save_asset(model_path, md)
    print(f"[INFO] saved {model_path}")
    print("[DONE] now AOT-compile and count ANE regions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
