#!/usr/bin/env python3
"""Score an HTTP-served embedder on the zoo's multilingual retrieval tasks.

The zoo's `_smoke/compare_embedders_retrieval.py` loads models with sentence-transformers, so it
cannot measure a model served from an ANE bundle. This reuses the zoo's OWN loader and its OWN
`ndcg_at_k` -- imported, not re-implemented -- so the data, the subsets and the metric are identical
to the published table, and only the embedding backend differs.

usage:
    python bench/eval_ane_embedder.py --endpoint http://127.0.0.1:8976 \
        --datasets NanoSciFact JaQuAD MIRACL-ja --max-queries 250 --corpus-pool 8000
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent
ZOO_SMOKE = ROOT / "repos" / "coreai-model-zoo" / "_smoke" / "compare_embedders_retrieval.py"


def load_zoo_helpers():
    """Import the zoo's loader and metric so they are literally the same code."""
    spec = importlib.util.spec_from_file_location("zoo_cmp", ZOO_SMOKE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["zoo_cmp"] = mod
    spec.loader.exec_module(mod)
    return mod


def post(url: str, payload: dict, timeout: int = 1800, attempts: int = 5):
    last = None
    for i in range(attempts):
        try:
            r = requests.post(url, json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001
            last = exc
            import time
            time.sleep(1.0 + i)
    raise RuntimeError(f"{attempts} attempts failed: {last}")


def embed_many(endpoint: str, texts: list[str], kind: str, batch: int = 32) -> np.ndarray:
    out = []
    for i in range(0, len(texts), batch):
        d = post(f"{endpoint}/v1/embeddings", {"input": texts[i:i + batch], "kind": kind})
        out.extend(e["embedding"] for e in d["data"])
    v = np.asarray(out, dtype=np.float32)
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.maximum(n, 1e-12)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://127.0.0.1:8976")
    ap.add_argument("--label", default="embeddinggemma-300m-ane")
    ap.add_argument("--datasets", nargs="+", default=["NanoSciFact"])
    ap.add_argument("--max-queries", type=int, default=250)
    ap.add_argument("--corpus-pool", type=int, default=8000)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    zoo = load_zoo_helpers()
    results = {}
    for ds in args.datasets:
        queries, corpus, qrels, hard = zoo.load_retrieval(ds)
        if args.max_queries or args.corpus_pool:
            queries, corpus, qrels = zoo.subset(queries, corpus, qrels,
                                                args.max_queries, args.corpus_pool, hard)
        qids = list(queries)
        dids = list(corpus)
        qtexts = [queries[q] if isinstance(queries[q], str) else queries[q].get("text", "")
                  for q in qids]
        dtexts = [corpus[d] if isinstance(corpus[d], str)
                  else (corpus[d].get("title", "") + " " + corpus[d].get("text", "")).strip()
                  for d in dids]
        print(f"\n=== {ds}: {len(qids)} queries, {len(dids)} docs ===", flush=True)
        dv = embed_many(args.endpoint, dtexts, "document")
        qv = embed_many(args.endpoint, qtexts, "query")
        nd, r10, top1 = [], [], []
        for i, q in enumerate(qids):
            scores = dv @ qv[i]
            order = np.argsort(-scores)[:10]
            ranked = [dids[j] for j in order]
            rel = {str(x) for x in (qrels.get(q, {}) if isinstance(qrels.get(q), dict)
                                    else qrels.get(q, []))}
            nd.append(zoo.ndcg_at_k(ranked, rel, 10))
            r10.append(len(set(ranked) & rel) / len(rel) if rel else 0.0)
            top1.append(1.0 if ranked and ranked[0] in rel else 0.0)
        results[ds] = {"ndcg@10": float(np.mean(nd)), "recall@10": float(np.mean(r10)),
                       "top1": float(np.mean(top1)), "dim": int(qv.shape[1])}
        print(f"  {args.label:38} {qv.shape[1]:5d} {np.mean(nd):8.4f} {np.mean(r10):7.4f} "
              f"{np.mean(top1):7.4f}", flush=True)

    out = args.out or (ROOT / "work" / "mteb" / f"ane_{args.label}.json")
    out.write_text(json.dumps({"label": args.label, "results": results}, indent=2))
    print(f"\n  wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
