#!/usr/bin/env python3
"""Von-1.0 (ModernBERT-Large decision model) as a static graph for the Neural Engine.

Von is a **non-autoregressive System One decision model**: one forward pass, no KV cache, no
token-by-token decoding, ~18 ms. Its backbone is **ModernBERT-Large** — the same architecture family
as our Granite embedder, which we already drive onto the ANE — so this is a port with a template
rather than a from-scratch build.

Graph:
    input_ids [1,S] int32, attention_mask [1,S] int32
      -> embeddings
      -> 28 ModernBERT layers (sliding/full alternating, RoPE, GELU MLP)
      -> masked MEAN pooling
      -> prediction head: dense(1024->1024) -> GELU -> LayerNorm
      -> classifier(1024->3) = [entailment, neutral, contradiction]
      -> PADDED to 32 wide (the alignment rule wants >= 32 fp16 on the last axis)

Adapted from the zoo's `conversion/granite_embedding/_granite_model.py`, which already solves the
ModernBERT traps this session ran into the hard way:
  * RoPE cos/sin are **precomputed buffers**, not gathered in-graph (the F-34 segfault)
  * layer 0 has **no attention norm** ("HF omits the first attention norm")
  * fused Wqkv and fused Wi -> chunk(2)
  * explicit matmul + fp32 softmax, **no fused SDPA**

Differences from Granite, taken from Von's own config/weights, not assumed:
  * `hidden_activation: gelu` (Granite is silu)
  * `classifier_pooling: mean` (Granite is CLS)
  * a 3-way classifier head instead of L2-normalised pooling

usage:
    python bench/export_von_ane.py --seq-len 256 --output-dir work/exports/von-ane
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
SRC = ROOT / "repos" / "coreai-model-kit"  # placeholder; set below
COREMODELS_SRC = (ROOT / "repos" / "coreai-kit" / "Examples" / "ChatDemo" / ".build"
                  / "checkouts" / "coreai-models" / "python" / "src")
MODEL_DIR = ROOT / "models" / "von-1.0"
if str(COREMODELS_SRC) not in sys.path:
    sys.path.insert(0, str(COREMODELS_SRC))
PAD_TO = 32          # output width, for the >=32 fp16 (64 B) last-axis rule


VARIANTS = {
    "v0": "as-is (fp32 softmax, float-literal scale, fp32 mask/pool literals)",
    "v1": "+ softmax in the graph dtype (drop dtype=torch.float32)",
    "v2": "+ scale + rope as f16 buffers (drop the ** -0.5 float literal)",
    "v3": "+ pooling/mask literals as dtype-matched tensors",
}
V = {"softmax_f32": True, "float_scale": True, "f16_buffers": False, "dtype_literals": False}


def _set_variant(name: str) -> None:
    V["softmax_f32"] = name == "v0"
    V["float_scale"] = name in ("v0", "v1")
    V["f16_buffers"] = name in ("v2", "v3")
    V["dtype_literals"] = name == "v3"


def _rotate_half(x: torch.Tensor) -> torch.Tensor:
    x1, x2 = x.chunk(2, dim=-1)
    return torch.cat((-x2, x1), dim=-1)


class Attention(nn.Module):
    """ModernBERT attention: fused Wqkv, RoPE from buffers, explicit matmul (no SDPA)."""

    def __init__(self, cfg: dict, seq_len: int, layer_id: int) -> None:
        super().__init__()
        self.hidden_size = cfg["hidden_size"]
        self.num_heads = cfg["num_attention_heads"]
        self.head_dim = self.hidden_size // self.num_heads
        self.seq_len = seq_len
        self.Wqkv = nn.Linear(self.hidden_size, 3 * self.hidden_size, bias=False)
        self.Wo = nn.Linear(self.hidden_size, self.hidden_size, bias=False)
        # scale as a dtype-matched BUFFER, not a Python float literal (v2)
        self.register_buffer("_scale", torch.tensor(self.head_dim ** -0.5,
                                                    dtype=torch.float16), persistent=False)

        # layer_types is explicit in Von's config; fall back to the every-N rule.
        types = cfg.get("layer_types")
        if types:
            self.is_local = types[layer_id] != "full_attention"
        else:
            self.is_local = layer_id % cfg["global_attn_every_n_layers"] != 0

        rp = cfg.get("rope_parameters", {}).get("full_attention", {})
        theta = float(rp.get("rope_theta", 10000.0)) if not self.is_local else 10000.0
        inv_freq = 1.0 / (theta ** (
            torch.arange(0, self.head_dim, 2, dtype=torch.int64).float() / self.head_dim))
        pos = torch.arange(seq_len).unsqueeze(0)
        freqs = (inv_freq[None, :, None] @ pos[:, None, :].float()).transpose(1, 2)
        angles = torch.cat((freqs, freqs), dim=-1).unsqueeze(1)
        # precomputed, NOT gathered in-graph -- the F-34 lesson
        cos, sin = angles.cos(), angles.sin()
        if V["f16_buffers"]:
            cos, sin = cos.to(torch.float16), sin.to(torch.float16)
        self.register_buffer("rope_cos", cos, persistent=False)
        self.register_buffer("rope_sin", sin, persistent=False)

    def forward(self, x, global_mask, local_mask):
        B = x.shape[0]
        qkv = self.Wqkv(x).reshape(B, self.seq_len, 3, self.num_heads, self.head_dim)
        q, k, v = qkv.transpose(3, 1).unbind(dim=2)
        cos, sin = self.rope_cos.to(q.dtype), self.rope_sin.to(q.dtype)
        q = q * cos + _rotate_half(q) * sin
        k = k * cos + _rotate_half(k) * sin
        scale = self._scale.to(q.dtype) if V["float_scale"] is False else (self.head_dim ** -0.5)
        scores = torch.matmul(q, k.transpose(2, 3)) * scale
        scores = scores + (local_mask if self.is_local else global_mask)
        if V["softmax_f32"]:
            probs = F.softmax(scores, dim=-1, dtype=torch.float32).to(q.dtype)
        else:
            probs = F.softmax(scores, dim=-1)
        out = torch.matmul(probs, v).transpose(1, 2).contiguous().reshape(B, self.seq_len, -1)
        return self.Wo(out)


class MLP(nn.Module):
    """ModernBERT MLP with Von's activation (GELU, per `hidden_activation`)."""

    def __init__(self, cfg: dict, act: str) -> None:
        super().__init__()
        self.Wi = nn.Linear(cfg["hidden_size"], 2 * cfg["intermediate_size"], bias=False)
        self.Wo = nn.Linear(cfg["intermediate_size"], cfg["hidden_size"], bias=False)
        self.act = act

    def forward(self, x):
        inputs, gate = self.Wi(x).chunk(2, dim=-1)
        h = F.gelu(inputs) if self.act == "gelu" else F.silu(inputs)
        return self.Wo(h * gate)


def layer_norm(cfg: dict) -> nn.LayerNorm:
    # Von sets norm_bias: False -- the checkpoint has no norm biases, so neither may the graph
    return nn.LayerNorm(cfg["hidden_size"], eps=cfg["layer_norm_eps"],
                        elementwise_affine=True, bias=bool(cfg.get("norm_bias", False)))


class Layer(nn.Module):
    def __init__(self, cfg: dict, seq_len: int, layer_id: int, act: str) -> None:
        super().__init__()
        # HF omits the first attention norm -- Von's weights have 27 attn_norms, not 28
        self.attn_norm = nn.Identity() if layer_id == 0 else layer_norm(cfg)
        self.attn = Attention(cfg, seq_len, layer_id)
        self.mlp_norm = layer_norm(cfg)
        self.mlp = MLP(cfg, act)

    def forward(self, x, gm, lm):
        x = x + self.attn(self.attn_norm(x), gm, lm)
        return x + self.mlp(self.mlp_norm(x))


class VonANE(nn.Module):
    def __init__(self, cfg: dict, seq_len: int) -> None:
        super().__init__()
        self.seq_len = seq_len
        self.hidden_size = cfg["hidden_size"]
        act = cfg.get("hidden_activation", "gelu")
        self.tok_embeddings = nn.Embedding(cfg["vocab_size"], cfg["hidden_size"])
        self.emb_norm = layer_norm(cfg)
        self.layers = nn.ModuleList(
            [Layer(cfg, seq_len, i, act) for i in range(cfg["num_hidden_layers"])])
        self.final_norm = layer_norm(cfg)
        # prediction head: dense -> act(gelu) -> norm
        self.head_dense = nn.Linear(cfg["hidden_size"], cfg["hidden_size"],
                                    bias=bool(cfg.get("classifier_bias", False)))
        self.head_norm = layer_norm(cfg)
        # classifier -> 3 logits, PADDED to PAD_TO for 64-byte alignment
        self.classifier = nn.Linear(cfg["hidden_size"], 3)

        pos = torch.arange(seq_len)
        dist = (pos[:, None] - pos[None, :]).abs()
        self.register_buffer("local_allowed",
                             (dist <= cfg["local_attention"] // 2)[None, None], persistent=False)

    def _masks(self, attention_mask):
        dtype = self.tok_embeddings.weight.dtype
        minimum = (torch.full((), torch.finfo(dtype).min, dtype=dtype)
                   if V["dtype_literals"] else torch.finfo(dtype).min)
        B = attention_mask.shape[0]           # batch = options in one call (see --batch)
        m = attention_mask[:, None, None, :].to(dtype).expand(B, 1, self.seq_len, self.seq_len)
        inv = 1.0 - m
        gm = inv.masked_fill(inv.to(torch.bool), minimum)
        lm = gm.masked_fill(~self.local_allowed, minimum)
        return gm, lm

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        gm, lm = self._masks(attention_mask)
        x = self.emb_norm(self.tok_embeddings(input_ids))
        for layer in self.layers:
            x = layer(x, gm, lm)
        x = self.final_norm(x)
        # masked MEAN pooling (Von: classifier_pooling = mean)
        w = attention_mask.unsqueeze(-1).to(x.dtype)
        denom = w.sum(dim=1)
        if V["dtype_literals"]:
            denom = denom.clamp_min(torch.ones((), dtype=denom.dtype))
        else:
            denom = denom.clamp_min(1.0)
        pooled = (x * w).sum(dim=1) / denom
        h = F.gelu(self.head_dense(pooled))
        h = self.head_norm(h)
        logits = self.classifier(h)                                   # (1, 3)
        # pad the last axis to 32 (>= 32 fp16 = 64 B, per the alignment rule)
        return F.pad(logits, (0, PAD_TO - logits.shape[-1]))

    # ---------------------------------------------------------------- weights
    @torch.no_grad()
    def load_hf(self, hf) -> None:
        sd = hf.state_dict()
        self.tok_embeddings.weight.copy_(sd["model.embeddings.tok_embeddings.weight"])
        self.emb_norm.weight.copy_(sd["model.embeddings.norm.weight"])
        for i, layer in enumerate(self.layers):
            p = f"model.layers.{i}"
            layer.attn.Wqkv.weight.copy_(sd[f"{p}.attn.Wqkv.weight"])
            layer.attn.Wo.weight.copy_(sd[f"{p}.attn.Wo.weight"])
            layer.mlp.Wi.weight.copy_(sd[f"{p}.mlp.Wi.weight"])
            layer.mlp.Wo.weight.copy_(sd[f"{p}.mlp.Wo.weight"])
            layer.mlp_norm.weight.copy_(sd[f"{p}.mlp_norm.weight"])
            if i > 0:
                layer.attn_norm.weight.copy_(sd[f"{p}.attn_norm.weight"])
        self.final_norm.weight.copy_(sd["model.final_norm.weight"])
        self.head_dense.weight.copy_(sd["head.dense.weight"])
        self.head_norm.weight.copy_(sd["head.norm.weight"])
        for mod, key in ((self.head_dense, "head.dense"), (self.head_norm, "head.norm")):
            if mod.bias is not None:
                mod.bias.copy_(sd[f"{key}.bias"])
        self.classifier.weight.copy_(sd["classifier.weight"])
        self.classifier.bias.copy_(sd["classifier.bias"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seq-len", type=int, default=256)
    ap.add_argument("--output-dir", type=Path, default=ROOT / "work" / "exports" / "von-ane")
    ap.add_argument("--variant", choices=list(VARIANTS), default="v0",
                    help="fp32-ism ladder, same shape as bench/granite_ane_variants.py")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--batch", type=int, default=1,
                    help="score this many options per graph call (1 = Von's NLI one-pass-per-option)")
    args = ap.parse_args()

    _set_variant(args.variant)
    print(f"[INFO] variant {args.variant}: {VARIANTS[args.variant]}")
    cfg = json.loads((MODEL_DIR / "config.json").read_text())
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    print("[INFO] loading Von (fp32, CPU) ...")
    hf = AutoModelForSequenceClassification.from_pretrained(
        MODEL_DIR, dtype=torch.float32).eval()
    tok = AutoTokenizer.from_pretrained(MODEL_DIR)

    module = VonANE(cfg, args.seq_len)
    module.load_hf(hf)
    module.eval()

    # ---- torch gate: does the re-authored graph match HF? ----
    CASES = [
        ("blocking", "Is this issue blocking customer operations?",
         "Connection pool exhausted on port 5432; handshakes timing out."),
        ("unrelated", "Is this issue blocking customer operations?",
         "The invoice PDF uses a serif font in the header."),
        ("contradiction", "The service is healthy.",
         "The service has been down for three hours with no recovery."),
    ]
    print(f"\n{'case':<16}{'HF argmax':>12}{'ours argmax':>14}{'max|dlogit|':>13}")
    worst = 0.0
    labels = {int(k): v for k, v in cfg["id2label"].items()}
    with torch.no_grad():
        for name, q, d in CASES:
            enc = tok(q, d, return_tensors="pt", truncation=True, max_length=args.seq_len)
            ids = enc["input_ids"]
            am = enc["attention_mask"]
            # pad to the fixed grid
            real = ids.shape[1]
            ids = F.pad(ids, (0, args.seq_len - real), value=cfg["pad_token_id"])
            am = F.pad(am, (0, args.seq_len - real), value=0)
            ref = hf(input_ids=ids, attention_mask=am).logits[0]
            got = module(ids, am)[0, :3]
            dl = float((ref - got).abs().max())
            worst = max(worst, dl)
            print(f"{name:<16}{labels[int(ref.argmax())]:>12}{labels[int(got.argmax())]:>14}{dl:>13.2e}")
    print(f"\n  worst |dlogit| = {worst:.2e}")
    if worst >= 1e-2:
        print("  FAIL: the re-authored graph diverges from HF")
        return 1

    # The comparison above is batch-1 only. When exporting a batched graph, prove the batched
    # shape too: every row receives the SAME input, so every row must reproduce the batch-1
    # result. Without this a `--batch > 1` export ships numerically unchecked.
    if args.batch > 1:
        got_b = module(ids.repeat(args.batch, 1), am.repeat(args.batch, 1))[:, :3]
        row_dev = float((got_b - got).abs().max())
        spread = float((got_b.max(0).values - got_b.min(0).values).abs().max())
        print(f"  batched shape ({args.batch} rows): |batched - batch1| = {row_dev:.2e}   "
              f"row spread = {spread:.2e}")
        if row_dev >= 1e-2 or spread >= 1e-2:
            print("  FAIL: the batched graph disagrees with the batch-1 graph")
            return 1

    print("  PASS: re-authored graph matches HF")

    del hf
    import gc
    gc.collect()

    # ---- export ----
    from coreai.runtime import AIModelAssetMetadata
    from coreai_torch import TorchConverter, get_decomp_table

    enc = tok(CASES[0][1], CASES[0][2], return_tensors="pt",
              truncation=True, max_length=args.seq_len)
    ids0 = F.pad(enc["input_ids"], (0, args.seq_len - enc["input_ids"].shape[1]),
                 value=cfg["pad_token_id"])
    am0 = F.pad(enc["attention_mask"], (0, args.seq_len - enc["attention_mask"].shape[1]), value=0)

    module = module.half()
    print("\n[INFO] torch.export ...")
    if args.batch > 1:
        ids0 = ids0.repeat(args.batch, 1)
        am0 = am0.repeat(args.batch, 1)
        print(f"[INFO] batched export: {args.batch} options per graph call")
    exported = torch.export.export(module, args=(ids0, am0))
    exported = exported.run_decompositions(get_decomp_table())
    print("[INFO] converting to Core AI ...")
    conv = TorchConverter().add_exported_program(
        exported_program=exported, input_names=["input_ids", "attention_mask"],
        output_names=["logits"])
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "coreai_mlir_ops", COREMODELS_SRC / "coreai_models" / "export" / "mlir_ops.py")
    mlir_ops = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mlir_ops)
    mlir_ops.register_custom_torch_lowering(conv)
    prog = conv.to_coreai()
    prog.optimize()

    out_dir = args.output_dir
    model_path = out_dir / f"von-1.0_{args.variant}_float16_s{args.seq_len}_ane.aimodel"
    if model_path.exists():
        if not args.overwrite:
            print(f"  {model_path} exists; pass --overwrite"); return 2
        shutil.rmtree(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    md = AIModelAssetMetadata()
    md.author = "wfzyx (Von), re-authored for the ANE"
    md.license = "Apache-2.0"
    md.model_description = (
        "Von-1.0 non-autoregressive System One decision model (ModernBERT-Large), re-authored for "
        "the Neural Engine: RoPE as buffers, layer-0 norm omitted, GELU MLP, mean pooling, 3-way "
        "classifier padded to 32. Source: https://github.com/wfzyx/von")
    md.creation_date = int(time.time())
    prog.save_asset(model_path, md)
    print(f"[INFO] saved {model_path}")
    print("[DONE] now AOT-compile and count ANE regions (0 = silent fallback = FAIL)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
