#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["mteb>=2.0", "requests", "numpy"]
# ///
"""Does indexing chunks SEPARATELY beat truncating at the grid?

EXP-009 measured a truncation curve; EXP-010 showed that pooling chunks into one vector loses to
truncation at every grid, and concluded that the real fix for long documents is to index each
chunk separately so a query can match the best chunk directly rather than a blur of all of them.
That conclusion was an inference, not a measurement -- this is the measurement.

MTEB cannot express it: its retrieval scores one vector per corpus entry, and our server's
/v1/embeddings returns one vector per input. So this does the retrieval by hand:

  1. every document is split into SEQ_LEN-2-token chunks, each chunk embedded separately
     (POST /v1/chunk_embeddings returns them unpooled),
  2. a document's score for a query is the MAX cosine over its chunks,
  3. rank, then compute ndcg@10 and recall@100 exactly as MTEB does.

usage:
    uv run bench/chunk_indexed_retrieval.py --endpoint http://127.0.0.1:8975 --seq-len 128
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
    """The text MTEB would encode for a corpus entry."""
    if isinstance(entry, str):
        return entry
    text = entry.get("text", "")
    title = entry.get("title") or ""
    return f"{title} {text}".strip() if title else text


def query_text(entry) -> str:
    return entry if isinstance(entry, str) else entry.get("text", "")


def post(url: str, payload: dict, timeout: int = 600, attempts: int = 6):
    """POST with retries. The server re-execs itself to recycle its IOSurface pool, and there is a
    brief window during the exec where the connection is refused; without retries a long run dies
    at the first recycle boundary."""
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
    """One (n_chunks, dim) array per input, chunks L2-normalized by the server."""
    out = []
    for i in range(0, len(texts), batch):
        d = post(url, {"input": texts[i:i + batch]}, timeout=1800)
        out.extend(np.asarray(e["embeddings"], dtype=np.float32) for e in d["data"])
    return out


def ndcg_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 2) for i, d in enumerate(ranked_ids[:k]) if d in relevant)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / idcg if idcg else 0.0


def recall_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(set(ranked_ids[:k]) & relevant) / len(relevant)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://127.0.0.1:8975")
    ap.add_argument("--task", default="SciFact")
    ap.add_argument("--seq-len", type=int, default=128)
    ap.add_argument("--limit", type=int, default=0, help="cap the corpus (0 = all)")
    ap.add_argument("--mode", choices=["chunked", "truncate"], default="chunked",
                    help="truncate = ONE vector per doc via /v1/embeddings (the MTEB baseline "
                         "mode), so this harness can be cross-checked against MTEB's own number")
    args = ap.parse_args()

    import mteb
    task = mteb.get_task(args.task)
    task.load_data()
    # MTEB 2.x: task.dataset is {config: {split: {corpus, queries, relevant_docs, ...}}}
    configs = task.dataset
    splits = configs.get("default", configs)
    split = "test" if "test" in splits else list(splits.keys())[0]
    data = splits[split]
    print(f"task {args.task}: split={split}, parts={sorted(data.keys())}")

    corpus_rows = data["corpus"]
    query_rows = data["queries"]
    qrels = data.get("relevant_docs") or data.get("qrels")
    doc_ids = [str(r["id"]) for r in corpus_rows]
    if args.limit:
        doc_ids = doc_ids[:args.limit]
    by_id = {str(r["id"]): r for r in corpus_rows}
    q_ids = [str(r["id"]) for r in query_rows]
    q_by_id = {str(r["id"]): r for r in query_rows}
    # relevant_docs may be {qid: [...]}, {qid: {docid: score}}, or a row-per-entry dataset
    if qrels is None:
        rel: dict = {}
    elif isinstance(qrels, dict):
        rel = {str(k): v for k, v in qrels.items()}
    else:
        rel = {str(r["id"]): r for r in qrels}

    def relevant_for(qid: str) -> set[str]:
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

    doc_texts = [corpus_text(by_id[i]) for i in doc_ids]
    q_texts = [query_text(q_by_id[i]) for i in q_ids]
    print(f"  {len(doc_ids)} docs, {len(q_ids)} queries, {len(rel)} qrels rows, grid S={args.seq_len}")

    # --- chunk index ---------------------------------------------------------
    if args.mode == "truncate":
        # ONE vector per doc (the server truncates at the grid) -- the same thing MTEB measures,
        # so a mismatch here means the two harnesses disagree, not the two methods.
        flat_docs = embed_many(f"{args.endpoint}/v1/embeddings", doc_texts, batch=64)
        chunked = [flat_docs[i:i + 1] for i in range(len(flat_docs))]
        print(f"  TRUNCATE mode: {flat_docs.shape[0]} vectors, 1 per doc")
    else:
        chunked = chunk_embed_many(f"{args.endpoint}/v1/chunk_embeddings", doc_texts)
    n_chunks = [c.shape[0] for c in chunked]
    print(f"  chunk index: {sum(n_chunks)} vectors for {len(doc_texts)} docs "
          f"({np.mean(n_chunks):.2f} chunks/doc, max {max(n_chunks)})")

    qv = embed_many(f"{args.endpoint}/v1/embeddings", q_texts)
    print(f"  queries embedded: {qv.shape}")

    # --- score: a doc's score is the MAX cosine over its chunks --------------
    ndcgs, recalls = [], []
    for qi, qid in enumerate(q_ids):
        scores = np.array([float((chunked[di] @ qv[qi]).max()) for di in range(len(doc_ids))])
        order = np.argsort(-scores)[:100]
        ranked = [doc_ids[j] for j in order]
        relevant = relevant_for(qid)
        ndcgs.append(ndcg_at_k(ranked, relevant, 10))
        recalls.append(recall_at_k(ranked, relevant, 100))

    nd, rc = float(np.mean(ndcgs)), float(np.mean(recalls))
    print(f"\n  chunk-indexed  ndcg@10 = {nd:.5f}   recall@100 = {rc:.4f}")
    print(f"  truncate S={args.seq_len}  (EXP-009/010 baselines)")
    out = ROOT / "work" / "mteb" / f"chunkindexed_s{args.seq_len}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"task": args.task, "seq_len": args.seq_len,
                               "ndcg_at_10": nd, "recall_at_100": rc,
                               "chunks": int(sum(n_chunks))}, indent=2))
    print(f"  wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
