#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["mteb>=2.0", "requests", "numpy"]
# ///
"""Does the cross-encoder reranker close the ndcg gap? (EXP-012)

EXP-011 left the pipeline at recall@100 = 0.9550 but ndcg@10 = 0.67923 -- the candidates are
retrieved, they are just not ordered. That is exactly what a reranker is for, and the oracle
headroom is +0.2758. This measures how much of it a real reranker captures.

The design isolates the reranker's effect: the SAME shortlist is scored twice -- once in the
retriever's own order, once in the reranker's order -- so the only thing that changes is the
ordering within the shortlist.

  1. chunk-index the corpus once (cached to .npz, since it costs ~80s)
  2. per query: rank all docs by max cosine over chunks, take the top K
  3. ndcg@10 / recall@10 on that shortlist, unreranked          <- the baseline
  4. rerank the shortlist with Qwen3-Reranker-0.6B, re-score    <- the treatment
  5. report both, plus how often the relevant doc was even IN the shortlist (the ceiling)

usage:
    uv run bench/rerank_retrieval.py --embed-endpoint http://127.0.0.1:8975 \
        --rerank-endpoint http://127.0.0.1:1977 --seq-len 128 --top-k 20 --queries 30
"""

from __future__ import annotations

import argparse
import json
import math
import time
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


def query_text(entry) -> str:
    return entry if isinstance(entry, str) else entry.get("text", "")


def post(url: str, payload: dict, timeout: int = 1800, attempts: int = 6):
    last = None
    for i in range(attempts):
        try:
            r = requests.post(url, json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.0 + i)
    raise RuntimeError(f"{attempts} attempts failed: {last}")


def embed_many(url: str, texts: list[str], batch: int = 64) -> np.ndarray:
    out = []
    for i in range(0, len(texts), batch):
        d = post(url, {"input": texts[i:i + batch]})
        out.extend(e["embedding"] for e in d["data"])
    return np.asarray(out, dtype=np.float32)


def chunk_embed_many(url: str, texts: list[str], batch: int = 16) -> list[np.ndarray]:
    out = []
    for i in range(0, len(texts), batch):
        d = post(url, {"input": texts[i:i + batch]})
        out.extend(np.asarray(e["embeddings"], dtype=np.float32) for e in d["data"])
    return out


def ndcg_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 2) for i, d in enumerate(ranked[:k]) if d in relevant)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / idcg if idcg else 0.0


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    return len(set(ranked[:k]) & relevant) / len(relevant) if relevant else 0.0


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
    if qrels is None:
        rel: dict = {}
    elif isinstance(qrels, dict):
        rel = {str(k): v for k, v in qrels.items()}
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--embed-endpoint", default="http://127.0.0.1:8975")
    ap.add_argument("--rerank-endpoint", default="http://127.0.0.1:1977")
    ap.add_argument("--task", default="SciFact")
    ap.add_argument("--seq-len", type=int, default=128)
    ap.add_argument("--top-k", type=int, default=20, help="shortlist size handed to the reranker")
    ap.add_argument("--queries", type=int, default=0, help="cap queries (0 = all)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    corpus_rows, query_rows, rel = load_task(args.task)
    doc_ids = [str(r["id"]) for r in corpus_rows]
    by_id = {str(r["id"]): r for r in corpus_rows}
    q_ids = [str(r["id"]) for r in query_rows]
    if args.queries:
        q_ids = q_ids[:args.queries]
    q_by_id = {str(r["id"]): r for r in query_rows}
    doc_texts = [corpus_text(by_id[i]) for i in doc_ids]
    q_texts = [query_text(q_by_id[i]) for i in q_ids]
    print(f"{args.task}: {len(doc_ids)} docs, {len(q_ids)} queries, grid S={args.seq_len}, "
          f"shortlist K={args.top_k}")

    # --- chunk index (cached) -------------------------------------------------
    cache = ROOT / "work" / "mteb" / f"chunkindex_cache_s{args.seq_len}.npz"
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        flat, starts = z["flat"], z["starts"]
        print(f"  chunk index: loaded {flat.shape[0]} vectors from cache")
    else:
        t0 = time.time()
        chunked = chunk_embed_many(f"{args.embed_endpoint}/v1/chunk_embeddings", doc_texts)
        starts = np.cumsum([0] + [c.shape[0] for c in chunked]).astype(np.int64)
        flat = np.concatenate(chunked, axis=0)
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache, flat=flat, starts=starts)
        print(f"  chunk index: {flat.shape[0]} vectors in {time.time() - t0:.0f}s (cached)")

    qv = embed_many(f"{args.embed_endpoint}/v1/embeddings", q_texts)

    # --- per query: shortlist, then rerank ------------------------------------
    base_nd, base_r10, rer_nd, rer_r10, in_short = [], [], [], [], []
    t_start = time.time()
    for qi, qid in enumerate(q_ids):
        scores = np.empty(len(doc_ids), dtype=np.float32)
        for di in range(len(doc_ids)):
            scores[di] = float((flat[starts[di]:starts[di + 1]] @ qv[qi]).max())
        order = np.argsort(-scores)[:args.top_k]
        shortlist = [doc_ids[j] for j in order]
        relevant = relevant_for(rel, qid)

        base_nd.append(ndcg_at_k(shortlist, relevant, 10))
        base_r10.append(recall_at_k(shortlist, relevant, 10))
        in_short.append(recall_at_k(shortlist, relevant, len(shortlist)))

        if not relevant:
            rer_nd.append(base_nd[-1]); rer_r10.append(base_r10[-1]); continue
        r = post(f"{args.rerank_endpoint}/v1/rerank",
                 {"query": q_texts[qi], "documents": [doc_texts[doc_ids.index(d)] for d in shortlist]})
        reranked = [shortlist[e["index"]] for e in r["results"]]
        rer_nd.append(ndcg_at_k(reranked, relevant, 10))
        rer_r10.append(recall_at_k(reranked, relevant, 10))

        if (qi + 1) % 5 == 0 or qi + 1 == len(q_ids):
            el = time.time() - t_start
            print(f"  {qi + 1}/{len(q_ids)} queries  ({el:.0f}s, {el / (qi + 1):.2f}s/query)  "
                  f"ndcg@10 {np.mean(base_nd):.4f} -> {np.mean(rer_nd):.4f}", flush=True)

    summary = {
        "task": args.task, "seq_len": args.seq_len, "top_k": args.top_k,
        "queries": len(q_ids),
        "baseline_ndcg_at_10": float(np.mean(base_nd)),
        "reranked_ndcg_at_10": float(np.mean(rer_nd)),
        "baseline_recall_at_10": float(np.mean(base_r10)),
        "reranked_recall_at_10": float(np.mean(rer_r10)),
        "relevant_in_shortlist": float(np.mean(in_short)),
        "seconds": time.time() - t_start,
    }
    print(f"\n  shortlist K={args.top_k}  ({len(q_ids)} queries)")
    print(f"    relevant doc in shortlist : {summary['relevant_in_shortlist']:.4f}  <- ceiling")
    print(f"    ndcg@10    baseline {summary['baseline_ndcg_at_10']:.5f} "
          f"-> reranked {summary['reranked_ndcg_at_10']:.5f}  "
          f"({summary['reranked_ndcg_at_10'] - summary['baseline_ndcg_at_10']:+.5f})")
    print(f"    recall@10  baseline {summary['baseline_recall_at_10']:.5f} "
          f"-> reranked {summary['reranked_recall_at_10']:.5f}  "
          f"({summary['reranked_recall_at_10'] - summary['baseline_recall_at_10']:+.5f})")

    out = args.out or (ROOT / "work" / "mteb" / f"rerank_k{args.top_k}.json")
    out.write_text(json.dumps(summary, indent=2))
    print(f"  wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
