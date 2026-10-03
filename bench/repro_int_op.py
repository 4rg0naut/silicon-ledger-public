#!/usr/bin/env python3
"""Minimal reproduction: Core ML conversion fails on `int()` shape-derived tensors.

Expected failure (numpy >= 2.4):
    ERROR - converting 'int' op (located at: 'model/embeddings/44')
    TypeError: only 0-dimensional arrays can be converted to Python scalars

No workaround is applied here on purpose — this is the upstream repro.

    python repro_int_op.py
"""
from __future__ import annotations

import sys

import numpy
import torch
import coremltools as ct
import transformers
from transformers import AutoModel, AutoTokenizer

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
SEQ = 128


class Wrapper(torch.nn.Module):
    """Mean-pooled sentence encoder — the standard shape for embedding models."""

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
    print(f"python       {sys.version.split()[0]}")
    print(f"numpy        {numpy.__version__}")
    print(f"torch        {torch.__version__}")
    print(f"coremltools  {ct.__version__}")
    print(f"transformers {transformers.__version__}")
    print(f"model        {MODEL}  seq={SEQ}")
    print("-" * 60)

    tok = AutoTokenizer.from_pretrained(MODEL)
    hf = AutoModel.from_pretrained(MODEL).eval()
    w = Wrapper(hf).eval()

    ids = torch.ones((1, SEQ), dtype=torch.int32)
    mask = torch.ones((1, SEQ), dtype=torch.int32)
    with torch.no_grad():
        traced = torch.jit.trace(w, (ids, mask), strict=False)

    try:
        ct.convert(
            traced,
            inputs=[
                ct.TensorType(name="input_ids", shape=[1, SEQ], dtype=numpy.int32),
                ct.TensorType(name="attention_mask", shape=[1, SEQ], dtype=numpy.int32),
            ],
            outputs=[ct.TensorType(name="embedding")],
            convert_to="mlprogram",
            minimum_deployment_target=ct.target.macOS13,
            compute_precision=ct.precision.FLOAT16,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"CONVERSION FAILED: {type(exc).__name__}: {exc}")
        return 1

    print("CONVERSION OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
