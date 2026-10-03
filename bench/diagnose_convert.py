#!/usr/bin/env python3
"""Diagnose the coremltools 'int()' conversion failure.

Prints the aten::Int nodes in the traced graph (with their scope + input dtypes)
and then tries conversion with alternative input dtypes.
"""
from __future__ import annotations

import numpy as np
import torch
import coremltools as ct
from transformers import AutoModel, AutoTokenizer

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
SEQ = 128


class Wrapper(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, input_ids, attention_mask):
        hidden = self.model(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        mask = attention_mask.unsqueeze(-1).to(hidden.dtype)
        summed = (hidden * mask).sum(dim=1)
        counts = mask.sum(dim=1).clamp(min=1e-9)
        return torch.nn.functional.normalize(summed / counts, p=2, dim=1)


def trace(mask_dtype):
    tok = AutoTokenizer.from_pretrained(MODEL)
    hf = AutoModel.from_pretrained(MODEL).eval()
    w = Wrapper(hf).eval()
    ids = torch.ones((1, SEQ), dtype=torch.int32)
    m = torch.ones((1, SEQ), dtype=mask_dtype)
    with torch.no_grad():
        t = torch.jit.trace(w, (ids, m), strict=False)
    return t, tok


def show_int_nodes(traced):
    print("--- nodes whose kind contains 'Int' ---")
    found = 0
    for node in traced.graph.nodes():
        if "Int" in node.kind() and node.kind() != "prim::Constant":
            found += 1
            ins = [(i.debugName(), getattr(i.type(), "dtype", lambda: None)()) for i in node.inputs()]
            print(f"  kind={node.kind()} scope={node.scopeName()} inputs={ins}")
    if not found:
        print("  (none)")


def try_convert(traced, mask_np_dtype, tag):
    try:
        ml = ct.convert(
            traced,
            inputs=[
                ct.TensorType(name="input_ids", shape=[1, SEQ], dtype=np.int32),
                ct.TensorType(name="attention_mask", shape=[1, SEQ], dtype=mask_np_dtype),
            ],
            outputs=[ct.TensorType(name="embedding")],
            convert_to="mlprogram",
            minimum_deployment_target=ct.target.macOS13,
            compute_precision=ct.precision.FLOAT16,
        )
        print(f"  [{tag}] CONVERT OK")
        return ml
    except Exception as exc:  # noqa: BLE001
        print(f"  [{tag}] FAILED: {type(exc).__name__}: {str(exc)[:110]}")
        return None


print("=== variant A: attention_mask int32 (as before) ===")
tA, _ = trace(torch.int32)
show_int_nodes(tA)
try_convert(tA, np.int32, "int32")

print("\n=== variant B: attention_mask float32 ===")
tB, tok = trace(torch.float32)
show_int_nodes(tB)
try_convert(tB, np.float32, "float32")

print("\n=== variant C: no attention_mask at all (fixed shape, mean over all) ===")


class WrapperNoMask(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, input_ids):
        hidden = self.model(input_ids=input_ids).last_hidden_state
        return torch.nn.functional.normalize(hidden.mean(dim=1), p=2, dim=1)


hf = AutoModel.from_pretrained(MODEL).eval()
wn = WrapperNoMask(hf).eval()
ids = torch.ones((1, SEQ), dtype=torch.int32)
with torch.no_grad():
    tC = torch.jit.trace(wn, (ids,), strict=False)
show_int_nodes(tC)
try:
    ml = ct.convert(
        tC,
        inputs=[ct.TensorType(name="input_ids", shape=[1, SEQ], dtype=np.int32)],
        outputs=[ct.TensorType(name="embedding")],
        convert_to="mlprogram",
        minimum_deployment_target=ct.target.macOS13,
        compute_precision=ct.precision.FLOAT16,
    )
    print("  [no-mask] CONVERT OK")
except Exception as exc:  # noqa: BLE001
    print(f"  [no-mask] FAILED: {type(exc).__name__}: {str(exc)[:110]}")
