#!/usr/bin/env python3
"""Locate the exact `int()` op that coremltools cannot convert.

Walks the traced graph (including sub-blocks), finds nodes whose kind mentions
"int", and reports each node's scope, input types, and — via TorchScript's
sourceRange — the original Python file and line that produced it.
"""
from __future__ import annotations

import torch
from transformers import AutoModel, AutoTokenizer

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
SEQ = 128


def walk(graph, depth=0):
    for node in graph.nodes():
        yield node, depth
        for block in node.blocks():
            yield from walk(block, depth + 1)


def main() -> int:
    tok = AutoTokenizer.from_pretrained(MODEL)
    hf = AutoModel.from_pretrained(MODEL).eval()

    enc = tok("hello world", return_tensors="pt", padding="max_length",
              truncation=True, max_length=SEQ)
    ids = enc["input_ids"].to(torch.int32)
    mask = enc["attention_mask"].to(torch.int32)

    with torch.no_grad():
        traced = torch.jit.trace(hf, (ids, mask), strict=False)

    print("=== nodes whose kind mentions 'int' ===")
    hits = 0
    for node, depth in walk(traced.graph):
        kind = node.kind()
        if "int" not in kind.lower():
            continue
        hits += 1
        print(f"\n[{hits}] kind={kind}  scope={node.scopeName()}  depth={depth}")
        for i in node.inputs():
            t = i.type()
            dtype = getattr(t, "dtype", lambda: None)()
            sizes = getattr(t, "sizes", lambda: None)()
            print(f"      input: {i.debugName()}  type={t}  dtype={dtype}  sizes={sizes}")
        try:
            sr = node.sourceRange()
            if sr:
                print(f"      source: {sr}")
        except Exception as exc:  # noqa: BLE001
            print(f"      source: unavailable ({exc})")

    if hits == 0:
        print("  (none found — try _get_trace_graph below)")

    print("\n=== same search via coremltools' tracing path ===")
    print("=== wrapper trace (reproduces the 'model/embeddings' scope) ===")

    class Wrapper(torch.nn.Module):
        def __init__(self, model):
            super().__init__()
            self.model = model

        def forward(self, input_ids, attention_mask):
            return self.model(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state

    w = Wrapper(hf).eval()
    with torch.no_grad():
        tw = torch.jit.trace(w, (ids, mask), strict=False)

    n = 0
    for node, depth in walk(tw.graph):
        if "int" not in node.kind().lower():
            continue
        n += 1
        info = []
        for i in node.inputs():
            t = i.type()
            info.append(f"{i.debugName()} sizes={getattr(t, 'sizes', lambda: None)()}")
        print(f"  [{n}] {node.kind()} scope={node.scopeName()}")
        for line in info:
            print(f"        {line}")
    if n == 0:
        print("  (none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
