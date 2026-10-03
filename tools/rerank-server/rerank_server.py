#!/usr/bin/env python3
"""Qwen3-Reranker-0.6B over HTTP, OpenAI-ish / Jina-ish rerank shape.

The cross-encoder that closes the loop after the ANE embedder: the embedder shortlists, this
re-scores the shortlist and returns P(yes) per (query, document) pair.

Two things this file exists to record, both measured on this machine:

1. **Run it on the GPU delegate, not the ANE.** The ANE delegate returns a CONSTANT [0.5, 0.5] for
   every pair -- no error, no warning, a plausible-looking "uncertain" score that would silently
   make the reranker a no-op (or worse, a random tie-breaker). Measured on the same pair:
       ANE [0.5, 0.5]   GPU [0.00619, 0.9937]   CPU [0.006306, 0.994]   official 0.993775
   The zoo's own gate and its latency numbers are GPU-delegate, so the ANE path was never
   validated for this bundle. GPU also loads in ~0.9s against the ANE's ~17s.

2. **Truncate the BODY only.** prefix + body + suffix; the prefix and suffix are kept whole and
   only the body is cut to fit the grid, because the suffix is what the model scores the next token
   of. (coreai-kit's Reranker.swift does the same.)

usage:
    python tools/rerank-server/rerank_server.py --port 1977
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_BUNDLE_DIR = ROOT / "models" / "qwen3-reranker"
AIMODEL_NAME = "qwen3-reranker-0.6b_float16_s512_static.aimodel"

SEQ_LEN = 512
PAD = 151643
MODEL_NAME = "qwen3-reranker-0.6b"


class Engine:
    """One loaded model + one event loop, shared by every request thread."""

    def __init__(self, bundle_dir: Path, model_name: str = MODEL_NAME,
                 restart_every: int = 4000) -> None:
        from tokenizers import Tokenizer
        from coreai.runtime import AIModel, NDArray, ComputeUnitKind, SpecializationOptions

        self.NDArray = NDArray
        self.model_name = model_name
        ref = json.loads((bundle_dir / "reference.json").read_text())
        self.prefix, self.suffix = ref["prefix"], ref["suffix"]
        self.instruction = ref["default_instruction"]
        self.yes_id, self.no_id, self.pad = ref["yes_id"], ref["no_id"], ref["pad_token_id"]

        self.tok = Tokenizer.from_file(str(bundle_dir / "tokenizer" / "tokenizer.json"))
        self.pre = self.tok.encode(self.prefix, add_special_tokens=False).ids
        self.suf = self.tok.encode(self.suffix, add_special_tokens=False).ids
        self.budget = SEQ_LEN - len(self.pre) - len(self.suf)
        if self.budget < 0:
            raise SystemExit(f"grid {SEQ_LEN} too small for the prompt scaffolding")

        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

        # GPU, not ANE -- see the module docstring.
        opts = SpecializationOptions.from_preferred_compute_unit_kind(ComputeUnitKind.gpu())
        self.model = self._run(AIModel.load(bundle_dir / AIMODEL_NAME, specialization_options=opts))
        self.fn = self.model.load_function("main")
        self._calls = 0
        self.restart_every = restart_every
        self.listen_fd = -1
        self._next_recycle = restart_every

    def maybe_recycle(self) -> None:
        """Recycle after the reply is flushed; the listening socket is inherited across the exec."""
        if not self.restart_every or self._calls < self._next_recycle:
            return
        self._next_recycle = self._calls + self.restart_every
        print(f"recycling after {self._calls} calls", flush=True)
        sys.stdout.flush()
        os.environ["RERANK_INHERIT_FD"] = str(self.listen_fd)
        os.set_inheritable(self.listen_fd, True)
        os.execv(sys.executable, [sys.executable, *sys.argv])

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()

    def score_one(self, query: str, document: str) -> float:
        body = f"<Instruct>: {self.instruction}\n<Query>: {query}\n<Document>: {document}"
        b = self.tok.encode(body, add_special_tokens=False).ids[:self.budget]
        ids = self.pre + b + self.suf
        real = len(ids)
        padded = ids + [self.pad] * (SEQ_LEN - real)
        mask = [1] * real + [0] * (SEQ_LEN - real)
        out = self._run(self.fn({
            "input_ids": self.NDArray(np.asarray([padded], dtype=np.int32)),
            "attention_mask": self.NDArray(np.asarray([mask], dtype=np.int32)),
        }))
        probs = out["probs"].numpy().reshape(-1)
        p = float(probs[1])          # [P(no), P(yes)]
        del out
        self._calls += 1
        if self._calls % 200 == 0:
            gc.collect()
        return p

    def rerank(self, query: str, documents: list[str], top_n: int = 0):
        scored = [(i, self.score_one(query, d)) for i, d in enumerate(documents)]
        scored.sort(key=lambda t: -t[1])
        return scored[:top_n] if top_n else scored


def make_handler(engine: Engine):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass

        def _send(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/health":
                self._send(200, {"status": "ok", "model": engine.model_name,
                                 "backend": "Core AI, GPU", "seq_len": SEQ_LEN,
                                 "body_budget": engine.budget})
            else:
                self._send(404, {"error": {"message": f"no route {self.path}"}})

        def do_POST(self) -> None:
            if self.path not in ("/v1/rerank", "/rerank"):
                self._send(404, {"error": {"message": f"no route {self.path}"}})
                return
            try:
                n = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(n) or b"{}")
            except Exception as exc:  # noqa: BLE001
                self._send(400, {"error": {"message": f"bad JSON: {exc}"}})
                return

            query = payload.get("query", "")
            docs = payload.get("documents", [])
            if isinstance(docs, str):
                docs = [docs]
            if not query or not docs:
                self._send(400, {"error": {"message": "need query and documents"}})
                return
            try:
                ranked = engine.rerank(query, docs, int(payload.get("top_n", 0)))
            except Exception as exc:  # noqa: BLE001
                self._send(500, {"error": {"message": f"{type(exc).__name__}: {exc}"}})
                return

            self._send(200, {
                "model": payload.get("model", engine.model_name),
                "results": [{"index": i, "relevance_score": s} for i, s in ranked],
                "usage": {"total_tokens": 0},
            })
            engine.maybe_recycle()

    return Handler


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE_DIR)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1977)
    ap.add_argument("--restart-every", type=int, default=4000,
                    help="recycle the process every N pair-scores (IOSurface pool); 0 disables")
    args = ap.parse_args()

    engine = Engine(args.bundle_dir, restart_every=args.restart_every)
    v = engine.score_one("warmup", "warmup")
    print(f"warmup score {v:.6f}", flush=True)

    inherited = os.environ.pop("RERANK_INHERIT_FD", None)
    if inherited:
        # Adopted from the previous incarnation: reuse the SAME socket, so no client is refused.
        # Creating a fresh ThreadingHTTPServer here fails with Errno 48 -- the inherited fd still
        # holds the port -- which killed a 300-query run at query 180.
        fd = int(inherited)
        sock = socket.fromfd(fd, socket.AF_INET, socket.SOCK_STREAM)
        httpd = ThreadingHTTPServer((args.host, args.port), make_handler(engine),
                                    bind_and_activate=False)
        httpd.socket.close()
        httpd.socket = sock
        httpd.server_address = sock.getsockname()
        httpd.server_activate()
        engine.listen_fd = sock.fileno()
        print(f"adopted inherited listening socket (fd {fd})", flush=True)
    else:
        httpd = ThreadingHTTPServer((args.host, args.port), make_handler(engine))
        engine.listen_fd = httpd.socket.fileno()

    print(f"ready: Qwen3-Reranker-0.6B on {args.host}:{args.port} (grid S={SEQ_LEN}, "
          f"body budget {engine.budget}, GPU)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
