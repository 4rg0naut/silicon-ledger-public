#!/usr/bin/env python3
"""The AOT-compiled ANE reranker over the same /v1/rerank API as the GPU server.

Exists so the retrieval pipeline can be pointed at the ANE instead of the GPU with no other change:
EXP-013 proved the ANE graph matches the published scores on the 6 reference pairs, but "the gate
passes" is not "the reranker works in the pipeline". This is what lets bench/rerank_retrieval.py
measure the ANE end to end.

Differences from tools/rerank-server/rerank_server.py (GPU):
  * loads the AOT .aimodelc, ANE delegate
  * RoPE cos/sin are computed HOST-SIDE and fed as inputs (the fix in EXP-013)
  * the last-token one-hot is computed HOST-SIDE and fed as an input
  * reads probs[:, 1] out of a 32-wide output (the head is padded for 64-byte alignment)

usage:
    python tools/rerank-server/rerank_server_ane.py --port 1978
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
BUNDLE_DIR = ROOT / "models" / "qwen3-reranker"
AIMODELC = (ROOT / "work" / "exports" / "reranker-ane" / "aot_h16g_ane"
            / "qwen3-reranker-0.6b_float16_s512_ane.h16g.aimodelc")
COREMODELS_SRC = (ROOT / "repos" / "coreai-kit" / "Examples" / "ChatDemo" / ".build"
                  / "checkouts" / "coreai-models" / "python" / "src")

SEQ_LEN = 512
MODEL_NAME = "qwen3-reranker-0.6b-ane"


def ane_causal_mask(seq_len: int) -> np.ndarray:
    k = np.arange(seq_len)[:, None]
    q = np.arange(seq_len)[None, :]
    m = np.where(k > q, np.float16(-40000.0), np.float16(0.0))
    return m[None, :, None, :]


class Engine:
    def __init__(self, model_name: str = MODEL_NAME, restart_every: int = 1500) -> None:
        from tokenizers import Tokenizer
        from coreai.runtime import AIModel, NDArray, ComputeUnitKind, SpecializationOptions

        self.NDArray = NDArray
        self.model_name = model_name
        ref = json.loads((BUNDLE_DIR / "reference.json").read_text())
        self.prefix, self.suffix = ref["prefix"], ref["suffix"]
        self.instruction = ref["default_instruction"]
        self.pad = ref["pad_token_id"]

        self.tok = Tokenizer.from_file(str(BUNDLE_DIR / "tokenizer" / "tokenizer.json"))
        self.pre = self.tok.encode(self.prefix, add_special_tokens=False).ids
        self.suf = self.tok.encode(self.suffix, add_special_tokens=False).ids
        self.budget = SEQ_LEN - len(self.pre) - len(self.suf)
        self.mask = ane_causal_mask(SEQ_LEN)

        import sys
        if str(COREMODELS_SRC) not in sys.path:
            sys.path.insert(0, str(COREMODELS_SRC))
        import torch
        from coreai_models.primitives.ios.rope import RoPECache
        rope = RoPECache(128, SEQ_LEN, 1_000_000.0)
        with torch.no_grad():
            rc, rs = rope.gather_cos_sin(torch.arange(SEQ_LEN).unsqueeze(0))
        self.rope_cos = rc.numpy().astype(np.float16)
        self.rope_sin = rs.numpy().astype(np.float16)

        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        opts = SpecializationOptions.from_preferred_compute_unit_kind(ComputeUnitKind.neural_engine())
        self.model = self._run(AIModel.load(AIMODELC, specialization_options=opts))
        self.fn = self.model.load_function("main")
        self._calls = 0
        self.restart_every = restart_every
        self.listen_fd = -1
        self._next_recycle = restart_every

    def maybe_recycle(self) -> None:
        """Recycle after the reply is flushed; the listening socket is inherited across the exec.

        Measured: without this the ANE reranker dies mid-run with
            CoreAIRuntime/NDArray+Pool.swift:77: Fatal error: Failed to allocate storage for
            NDArray with byteCount: 64, sk: ioSurface, st: float16
        which is the F-31 IOSurface pool again -- the runtime exposes no release API, so the process
        must re-exec. A 512-grid fp16 reranker burns the pool faster than the embedder does, so this
        recycles every 1500 calls rather than 4000."""
        if not self.restart_every or self._calls < self._next_recycle:
            return
        self._next_recycle = self._calls + self.restart_every
        print(f"recycling after {self._calls} calls", flush=True)
        sys.stdout.flush()
        os.environ["RERANK_ANE_INHERIT_FD"] = str(self.listen_fd)
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
        am = np.asarray([[1] * real + [0] * (SEQ_LEN - real)], dtype=np.int32)
        m = am.reshape(-1).astype(np.float16)
        zero = np.zeros_like(m[:1])
        last_token = (m * (1.0 - np.concatenate([m[1:], zero]))).reshape(1, -1).astype(np.float16)
        out = self._run(self.fn({
            "input_ids": self.NDArray(np.asarray([padded], dtype=np.int32)),
            "attention_mask": self.NDArray(am),
            "causal_mask": self.NDArray(self.mask),
            "last_token": self.NDArray(last_token),
            "rope_cos": self.NDArray(self.rope_cos),
            "rope_sin": self.NDArray(self.rope_sin),
        }))
        probs = out["probs"].numpy().reshape(-1)
        p = float(probs[1])          # row 1 = "yes"
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
                                 "backend": "Core AI, ANE (AOT)", "seq_len": SEQ_LEN})
            else:
                self._send(404, {"error": {"message": f"no route {self.path}"}})

        def do_POST(self) -> None:
            if self.path not in ("/v1/rerank", "/rerank"):
                self._send(404, {"error": {"message": f"no route {self.path}"}})
                return
            n = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(n) or b"{}")
            query = payload.get("query", "")
            docs = payload.get("documents", [])
            if isinstance(docs, str):
                docs = [docs]
            if not query or not docs:
                self._send(400, {"error": {"message": "need query and documents"}})
                return
            ranked = engine.rerank(query, docs, int(payload.get("top_n", 0)))
            self._send(200, {
                "model": payload.get("model", engine.model_name),
                "results": [{"index": i, "relevance_score": s} for i, s in ranked],
            })
            engine.maybe_recycle()

    return Handler


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1978)
    ap.add_argument("--restart-every", type=int, default=1500,
                    help="re-exec after N pair-scores: the ANE reranker exhausts the IOSurface "
                         "pool (F-31) and dies with NDArray+Pool.swift:77 otherwise")
    args = ap.parse_args()
    engine = Engine(restart_every=args.restart_every)
    inherited = os.environ.pop("RERANK_ANE_INHERIT_FD", None)
    if inherited:
        fd = int(inherited)
        sock = socket.fromfd(fd, socket.AF_INET, socket.SOCK_STREAM)
        httpd = ThreadingHTTPServer((args.host, args.port), make_handler(engine),
                                    bind_and_activate=False)
        httpd.socket.close(); httpd.socket = sock
        httpd.server_address = sock.getsockname(); httpd.server_activate()
        engine.listen_fd = sock.fileno()
        print(f"adopted inherited listening socket (fd {fd})", flush=True)
    else:
        httpd = ThreadingHTTPServer((args.host, args.port), make_handler(engine))
        engine.listen_fd = httpd.socket.fileno()
    print(f"ready: Qwen3-Reranker-0.6B on the ANE at {args.host}:{args.port} "
          f"(grid S={SEQ_LEN}, body budget {engine.budget})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
