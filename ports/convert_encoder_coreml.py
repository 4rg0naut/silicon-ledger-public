#!/usr/bin/env python3
"""Convert an HF sentence encoder to Core ML mlprogram for ANE measurement.

Key choices:
  * convert_to="mlprogram"  -> required for Neural Engine placement
                             (the legacy "neuralnetwork" format never uses ANE)
  * fixed (1, SEQ) shape    -> the ANE needs static shapes; RangeDim forces
                             fallback to CPU/GPU
  * mean-pool + L2 norm INSIDE the graph, so the whole sentence encoder is one
    ANE-friendly graph with a single output tensor.
"""
from __future__ import annotations

import argparse
import sys
import time

import numpy as np
import torch
import coremltools as ct
from transformers import AutoModel, AutoTokenizer

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def patch_embeddings(hf: torch.nn.Module) -> None:
    """Replace BertEmbeddings.forward with a trace-friendly equivalent.

    The stock implementation emits an `int()` op that coremltools 9 cannot
    convert (`TypeError: only 0-dimensional arrays ...`). We keep the real
    weights (word/position/token_type embeddings + LayerNorm) and only
    rewrite the arithmetic, which is what published Core ML BERT recipes do.
    """
    import types

    def forward(self, input_ids=None, token_type_ids=None, position_ids=None,
                inputs_embeds=None, past_key_values_length=0):
        if inputs_embeds is None:
            inputs_embeds = self.word_embeddings(input_ids)
        seq_len = inputs_embeds.shape[1]
        if position_ids is None:
            position_ids = torch.arange(seq_len, dtype=torch.long, device=inputs_embeds.device)
            position_ids = position_ids.unsqueeze(0)
        pos = self.position_embeddings(position_ids)
        if token_type_ids is None:
            token_type_ids = torch.zeros_like(input_ids)
        tok = self.token_type_embeddings(token_type_ids)
        emb = self.LayerNorm(inputs_embeds + pos + tok)
        return self.dropout(emb)

    hf.embeddings.forward = types.MethodType(forward, hf.embeddings)


class SentenceEncoder(torch.nn.Module):
    def __init__(self, model: torch.nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        hidden = self.model(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        mask = attention_mask.unsqueeze(-1).to(hidden.dtype)
        summed = (hidden * mask).sum(dim=1)
        counts = mask.sum(dim=1).clamp(min=1e-9)
        return torch.nn.functional.normalize(summed / counts, p=2, dim=1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--seq", type=int, default=128, help="fixed sequence length")
    ap.add_argument("--out", default=None)
    ap.add_argument("--dynamic", action="store_true", help="also emit a RangeDim variant")
    args = ap.parse_args()

    out = args.out or f"models/minilm{args.seq}.mlpackage"
    print(f"model      : {args.model}")
    print(f"seq length : {args.seq} (fixed)")
    print(f"output     : {out}")

    t0 = time.perf_counter()
    tok = AutoTokenizer.from_pretrained(args.model)
    hf = AutoModel.from_pretrained(args.model).eval()
    patch_embeddings(hf)
    n_params = sum(p.numel() for p in hf.parameters())
    print(f"loaded     : {n_params/1e6:.1f}M params in {time.perf_counter()-t0:.1f}s")

    wrapper = SentenceEncoder(hf).eval()

    ids = torch.ones((1, args.seq), dtype=torch.int32)
    mask = torch.ones((1, args.seq), dtype=torch.int32)
    with torch.no_grad():
        traced = torch.jit.trace(wrapper, (ids, mask), strict=False)
    print("traced ok")

    def convert(shape_ids, shape_mask, tag):
        ml = ct.convert(
            traced,
            inputs=[
                ct.TensorType(name="input_ids", shape=shape_ids, dtype=np.int32),
                ct.TensorType(name="attention_mask", shape=shape_mask, dtype=np.int32),
            ],
            outputs=[ct.TensorType(name="embedding")],
            convert_to="mlprogram",
            minimum_deployment_target=ct.target.macOS13,
            compute_precision=ct.precision.FLOAT16,
        )
        path = out if tag == "fixed" else out.replace(".mlpackage", "_dynamic.mlpackage")
        ml.save(path)
        print(f"saved {tag}: {path}")
        return ml, path

    ml, path = convert([1, args.seq], [1, args.seq], "fixed")
    if args.dynamic:
        convert(
            [1, ct.RangeDim(1, args.seq)],
            [1, ct.RangeDim(1, args.seq)],
            "dynamic",
        )

    # sanity check: real sentence -> embedding, vs the torch reference
    text = "The neural engine accelerates dense matrix multiplication."
    enc = tok(text, return_tensors="pt", padding="max_length", truncation=True, max_length=args.seq)
    ref = wrapper(enc["input_ids"].to(torch.int32), enc["attention_mask"].to(torch.int32)).detach().numpy()[0]

    got = ml.predict(
        {
            "input_ids": enc["input_ids"].numpy().astype(np.int32),
            "attention_mask": enc["attention_mask"].numpy().astype(np.int32),
        }
    )["embedding"][0]

    cos = float(np.dot(ref, got) / (np.linalg.norm(ref) * np.linalg.norm(got)))
    print(f"dims       : {got.shape[0]}")
    print(f"cosine(torch, coreml) = {cos:.6f}  (1.0 = identical)")
    if cos < 0.99:
        print("WARNING: conversion drift above tolerance", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
