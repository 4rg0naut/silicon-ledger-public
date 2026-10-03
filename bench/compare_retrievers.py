#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["mteb>=2.0", "requests", "numpy", "sentence-transformers>=3.0", "torch"]
# ///
"""Where do we actually stand? Same reranker, different retriever.

The earlier comparison was unfair: our *reranked* pipeline (0.75860) was set against bge-base
*unreranked* (0.74345). A reranked pipeline beating an unreranked model is not a result.

This isolates the two halves of our stack by holding the reranker fixed (our ANE reranker, K=20)
and swapping only the retriever:

    ours   (Granite-Embedding-97M, chunk-indexed, ANE)      -> ?
    bge-base-en-v1.5 (109M, one vector per doc)             -> ?

If bge-base + our reranker beats ours + our reranker, our retriever is the weak link and the
pipeline result was carried by the reranker. If they land together, the retriever is competitive.

usage:
    uv run bench/compare_retrievers.py --rerank-endpoint http://127.0.0.1:1978 --model BAAI/bge-base-en-v1.5
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent


def corpus_text(entry) -> str:
    if isinstance(entry, str):
        return entry
    text = entry.get("text", "")
    title = entry.get("title") or ""
    return f"{title} {text}".strip() if title else text


def load_task(name: str):
    import mteb
    task = mteb.get_task(name)
    task.load_data()
    configs = task.dataset
    splits = configs.get("default", configs)
    split = "test" if "test" in splits else list(splits.keys())[0]
    data = splits[split]
    corpus_rows, query_rows = data["corpus"], data["queries"]
    qrels = data.get("relevant_docs") or data.get("qrels")
    if isinstance(qrels, dict):
        rel = {str(k): v for k, v in qrels.items()}
    elif qrels is None:
        rel = {}
    else:
        rel = {str(r["id"]): r for r in qrels}
    return corpus_rows, query_rows, rel


def relevant_for(rel: dict, qid: str) -> set[str]:
    v = rel.get(qid)
    if v is None:
        return set()
    if isinstance(v, dict):
        for key in ("relevant_docs", "qrels", "relevant_ids", "doc_ids"):
            if key in v:
                inner = v[key]
                return {str(x) for x in (inner.keys() if isinstance(inner, dict) else inner)}
        return {str(x) for x in v.keys()}
    return {str(x) for x in v}


def ndcg_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 2) for i, d in enumerate(ranked[:k]) if d in relevant)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / idcg if idcg else 0.0


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    return len(set(ranked[:k]) & relevant) / len(relevant) if relevant else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rerank-endpoint", default="http://127.0.0.1:1978")
    ap.add_argument("--model", default="BAAI/bge-base-en-v1.5")
    ap.add_argument("--task", default="SciFact")
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    corpus_rows, query_rows, rel = load_task(args.task)
    doc_ids = [str(r["id"]) for r in corpus_rows]
    by_id = {str(r["id"]): r for r in corpus_rows}
    q_ids = [str(r["id"]) for r in query_rows]
    q_by_id = {str(r["id"]): r for r in query_rows}
    doc_texts = [corpus_text(by_id[i]) for i in doc_ids]
    q_texts = [corpus_text(q_by_id[i]) for i in q_ids]
    print(f"{args.task}: {len(doc_ids)} docs, {len(q_ids)} queries, retriever={args.model}")

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(args.model)
    print("  embedding corpus ...")
    dv = model.encode(doc_texts, batch_size=64, normalize_embeddings=True,
                      show_progress_bar=False).astype(np.float32)
    qv = model.encode(q_texts, batch_size=64, normalize_embeddings=True,
                      show_progress_bar=False).astype(np.float32)
    print(f"  corpus {dv.shape}  queries {qv.shape}")

    base_nd, base_r10, rer_nd, rer_r10, in_short = [], [], [], [], []
    for qi, qid in enumerate(q_ids):
        scores = dv @ qv[qi]
        order = np.argsort(-scores)[:args.top_k]
        shortlist = [doc_ids[j] for j in order]
        relevant = relevant_for(rel, qid)
        base_nd.append(ndcg_at_k(shortlist, relevant, 10))
        base_r10.append(recall_at_k(shortlist, relevant, 10))
        in_short.append(recall_at_k(shortlist, relevant, len(shortlist)))
        if not relevant:
            rer_nd.append(base_nd[-1]); rer_r10.append(base_r10[-1]); continue
        r = requests.post(f"{args.rerank_endpoint}/v1/rerank",
                          json={"query": q_texts[qi],
                                "documents": [doc_texts[doc_ids.index(d)] for d in shortlist]},
                          timeout=1800).json()
        reranked = [shortlist[e["index"]] for e in r["results"]]
        rer_nd.append(ndcg_at_k(reranked, relevant, 10))
        rer_r10.append(recall_at_k(reranked, relevant, 10))
        if (qi + 1) % 25 == 0:
            print(f"  {qi+1}/{len(q_ids)}  ndcg@10 {np.mean(base_nd):.4f} -> {np.mean(rer_nd):.4f}",
                  flush=True)

    summary = {
        "task": args.task, "retriever": args.model, "top_k": args.top_k,
        "queries": len(q_ids),
        "baseline_ndcg_at_10": float(np.mean(base_nd)),
        "reranked_ndcg_at_10": float(np.mean(rer_nd)),
        "baseline_recall_at_10": float(np.mean(base_r10)),
        "reranked_recall_at_10": float(np.mean(rer_r10)),
        "relevant_in_shortlist": float(np.mean(in_short)),
    }
    print(f"\n  retriever {args.model}")
    print(f"    ndcg@10    {summary['baseline_ndcg_at_10']:.5f} -> {summary['reranked_ndcg_at_10']:.5f}")
    print(f"    recall@10  {summary['baseline_recall_at_10']:.5f} -> {summary['reranked_recall_at_10']:.5f}")
    print(f"    ceiling    {summary['relevant_in_shortlist']:.4f}")
    out = args.out or (ROOT / "work" / "mteb"
                       / f"retriever_{args.model.split('/')[-1]}_k{args.top_k}.json")
    out.write_text(json.dumps(summary, indent=2))
    print(f"  wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
