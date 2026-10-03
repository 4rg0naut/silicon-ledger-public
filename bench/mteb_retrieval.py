#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["mteb>=2.0", "requests", "numpy"]
# ///
"""MTEB retrieval evaluation of the ANE embedding server.

The model card for this bundle says its retrieval quality was never measured — *"the fixture set
below is a parity instrument (35 texts, 4 queries, 12 documents), not a benchmark"*. This runs it
against MTEB, the field's standard, on tasks whose main score is `ndcg_at_10`.

The embedder is our own HTTP server (`tools/embed-server/embed_server.py`), which serves
Granite-Embedding-97M from the Neural Engine in OpenAI-compatible form. MTEB ships
`OpenAIAPIEncodeWrapper` for exactly that, so no custom protocol implementation is needed.
`use_chat_template=False` is required: the default routes text through a `messages` field that is
a vLLM extension our server does not implement.

IMPORTANT — the grid matters. The graph is a fixed grid (S=128 or S=512) and the tokenizer
truncates the body to S-2 tokens. SciFact passages run 150-200 words, so an S=128 build throws
away most of every document. Run both grids before drawing conclusions about the model; the S=128
number is a floor imposed by the artifact, not the model's quality.

usage:
    tools/memory-stack/start.sh                     # the embed server must be up
    uv run bench/mteb_retrieval.py --tasks SciFact --max-length 128

Note: pass the BASE url. MTEB appends `/v1/models` and `/v1/embeddings` itself, so a
trailing `/v1` yields a 404 on `/v1/v1/models`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mteb
from mteb.models import OpenAIAPIEncodeWrapper

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://127.0.0.1:8799",
                    help="server BASE url — MTEB appends /v1/models and /v1/embeddings itself")
    ap.add_argument("--model-name", default="granite-embedding-97m")
    ap.add_argument("--tasks", default="SciFact", help="comma-separated MTEB task names")
    ap.add_argument("--max-length", type=int, default=128,
                    help="the graph's fixed grid (must match the exported bundle)")
    ap.add_argument("--out", type=Path, default=ROOT / "work" / "mteb")
    args = ap.parse_args()

    model = OpenAIAPIEncodeWrapper(
        endpoint_url=args.endpoint,
        model_name=args.model_name,
        use_chat_template=False,      # not vLLM: plain `input`, not `messages`
        modalities=["text"],
        max_length=args.max_length,
    )

    task_names = [t.strip() for t in args.tasks.split(",") if t.strip()]
    tasks = [mteb.get_task(t) for t in task_names]
    for t in tasks:
        md = t.metadata
        print(f"task {md.name}: main_score={md.main_score} splits={md.eval_splits}")

    args.out.mkdir(parents=True, exist_ok=True)
    result = mteb.evaluate(model, tasks=tasks, overwrite_strategy="always",
                           encode_kwargs={"batch_size": 64})

    print("\n" + "=" * 76)
    print(f"MTEB retrieval — {args.model_name} on the ANE, grid S={args.max_length}")
    print("=" * 76)

    # ModelResult -> per-task results; walk whatever shape it exposes rather than assuming one.
    task_results = getattr(result, "task_results", None) or list(result) or []
    summary = {}
    for tr in task_results:
        name = getattr(getattr(tr, "task", None), "metadata", None)
        name = getattr(name, "name", str(tr))
        main = getattr(getattr(tr, "task", None), "metadata", None)
        main = getattr(main, "main_score", "ndcg_at_10")
        row = {}
        scores = getattr(tr, "scores", {}) or {}
        for split_scores in scores.values():
            for entry in split_scores:
                if isinstance(entry, dict):
                    row.update({k: v for k, v in entry.items() if isinstance(v, (int, float))})
        summary[name] = row
        print(f"  {name:<22} {main} = {row.get(main)}")
        for k in ("ndcg_at_10", "ndcg_at_100", "recall_at_10", "recall_at_100",
                  "map_at_10", "mrr_at_10"):
            if k in row and k != main:
                print(f"  {'':<22} {k} = {row[k]}")
    if not task_results:
        print(f"  (no task results; result type {type(result).__name__})")

    dest = args.out / f"summary_s{args.max_length}.json"
    dest.write_text(json.dumps(summary, indent=2))
    print(f"\nrecord: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
