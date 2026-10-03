#!/usr/bin/env python3
"""OpenAI-compatible /v1/embeddings backed by Granite-Embedding-97M on the Neural Engine.

WHY THIS EXISTS
    `mnemopi` (the local memory engine) takes embeddings either from its bundled `fastembed`
    ONNX path or from an OpenAI-compatible endpoint (`MNEMOPI_EMBEDDING_API_URL`). The bundled
    path works but crashes Bun on exit here (`panic: A C++ exception occurred` after the work is
    done, 0 crash lines with MNEMOPI_NO_EMBEDDINGS=1 — so it is the native ONNX module), and it
    runs on the CPU. This serves the same 384 dimensions from the ANE instead:

        Granite-Embedding-97M, fp16, 1 ANE region, ~2.1-3.9 ms per embedding on a base M4

    It is local end to end: 127.0.0.1, no cloud, no API key.

DIMENSIONS MATTER
    mnemopi's default (`BAAI/bge-small-en-v1.5`) is 384-dimensional and so is this, so the vector
    shape matches. The *semantics* do not: embeddings from two different models must not share a
    table. Point a fresh bank at this, or re-embed.

usage:
    .venv/bin/python tools/embed-server/embed_server.py --port 8799
    curl -s localhost:8799/v1/embeddings -H 'Content-Type: application/json' \
         -d '{"input":"hello world","model":"granite-embedding-97m"}' | head -c 200

env/args: --bundle, --tokenizer, --port, --host, --model-name
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import os
import socket
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
ZOO = ROOT / "repos" / "coreai-model-zoo"
sys.path.insert(0, str(ZOO / "conversion" / "granite_embedding"))

DEFAULT_BUNDLE = (ROOT / "work/exports/granite-embedding-97m/ane-sweep/v3/aot/"
                  "granite97m_fp16_s128_v3.h16g.aimodelc")
DEFAULT_TOKENIZER = ROOT / "models/granite97m/macos/fp32-s128/tokenizer"
# The graph is a FIXED grid: the exported bundle is S=128 or S=512 and the tokenizer truncates
# the body to S-2 tokens. This must match the bundle or the model sees garbage shapes.
SEQ_LEN = 128
CHUNK = False
POOL = "max"


class Engine:
    """One loaded model + one event loop, shared by every request thread."""

    def __init__(self, bundle: Path, tokenizer: Path, model_name: str,
                 restart_every: int = 4000) -> None:
        from coreai.runtime import AIModel, NDArray, ComputeUnitKind, SpecializationOptions
        from _granite_tokenizer import GraniteTokenizer

        self.NDArray = NDArray
        self.model_name = model_name
        self.tok = GraniteTokenizer(tokenizer)
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

        opts = SpecializationOptions.from_preferred_compute_unit_kind(ComputeUnitKind.neural_engine())
        self.model = self._run(AIModel.load(bundle, specialization_options=opts))
        self.fn = self.model.load_function("main")
        self._calls = 0
        self.restart_every = restart_every
        self.listen_fd = -1
        self._next_recycle = restart_every

    def maybe_recycle(self) -> None:
        """Recycle the process, but only AFTER the current response has been sent.

        The IOSurface pool is process-global and has no release API, so a long run must restart.
        Two things make that invisible to clients: the listening socket is inherited across the
        exec (see main()), and this runs after the reply is flushed -- recycling *before* serving
        drops the in-flight request, which measured as exactly 3 failures in 10,000 (at the
        recycle boundaries)."""
        # NOTE: use a THRESHOLD, not `_calls % restart_every == 0`. A batched client (MTEB sends
        # 64 texts per request) advances _calls in steps of 64, so a modulus on a round number
        # never matches and the recycle silently never fires -- the pool then exhausts mid-run.
        if not self.restart_every or self._calls < self._next_recycle:
            return
        self._next_recycle = self._calls + self.restart_every
        print(f"recycling after {self._calls} calls (IOSurface pool)", flush=True)
        sys.stdout.flush()
        os.environ["EMBED_INHERIT_FD"] = str(self.listen_fd)
        os.set_inheritable(self.listen_fd, True)
        os.execv(sys.executable, [sys.executable, *sys.argv])

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()

    def _embed_ids(self, active: list[int]) -> list[float]:
        """One graph call for one window of <= SEQ_LEN tokens (cls/body/sep, right-padded)."""
        ids = np.full((1, SEQ_LEN), self.tok.pad_id, dtype=np.int32)
        mask = np.zeros((1, SEQ_LEN), dtype=np.int32)
        ids[0, :len(active)] = active
        mask[0, :len(active)] = 1
        # The Core AI Python runtime exposes no way to release an NDArray, and the outputs are
        # IOSurface-backed (`sk: ioSurface, st: float16`). Under sustained load its pool is
        # exhausted and the process dies:
        #   "Fatal error: Failed to allocate storage for NDArray with byteCount: 768, sk: ioSurface"
        # Measured: ~5,500 embeddings is fine; the multilingual MTEB task (32,659) is not.
        # So the process re-execs itself every --restart-every calls. The specialization is
        # cached, so the reload is a few ms, and MTEB's client retries a dropped connection.
        out = self._run(self.fn({
            "input_ids": self.NDArray(ids.reshape(1, -1).astype(np.int32)),
            "attention_mask": self.NDArray(mask.reshape(1, -1).astype(np.int32)),
        }))
        vec = [float(x) for x in out["embedding"].numpy().reshape(-1)]
        del out
        self._calls += 1
        if self._calls % 500 == 0:
            gc.collect()
        return vec

    def embed_one(self, text: str) -> list[float]:
        """Embed one text.

        Default: the graph is a fixed grid, so the body is truncated to SEQ_LEN-2 tokens -- every
        token past the grid is silently discarded (this is what EXP-009's curve measures).

        With --chunk: the body is instead split into non-overlapping SEQ_LEN-2 windows, each is
        embedded, and the vectors are pooled (--pool max|mean) and re-normalized. Nothing is
        discarded, at the cost of ceil(n/win) graph calls instead of one.

        MEASURED WORSE (EXP-010): pooling a document into one vector loses to plain truncation on
        SciFact ndcg@10 at every grid -- mean-pool by 0.004/0.017/0.016 at S=128/256/512, max-pool
        by 0.086/0.032/0.007. recall@100 holds up while ndcg@10 drops, i.e. the evidence is in the
        index but can no longer be ranked first: a pooled vector is a blur of the document's parts.
        Kept because it is the mechanism that produced that result, and it is what a genuinely
        long-document corpus (where a 512 grid discards most of the input) would be tested with.
        """
        body = self.tok.encode_body(text)
        win = SEQ_LEN - 2
        if not CHUNK or len(body) <= win:
            return self._embed_ids([self.tok.cls_id, *body[:win], self.tok.sep_id])
        parts = [np.asarray(self._embed_ids([self.tok.cls_id, *body[i:i + win], self.tok.sep_id]),
                            dtype=np.float32)
                 for i in range(0, len(body), win)]
        stacked = np.stack(parts)
        pooled = stacked.mean(axis=0) if POOL == "mean" else stacked.max(axis=0)
        pooled /= np.linalg.norm(pooled) + 1e-12
        return [float(x) for x in pooled]

    def chunk_vectors(self, text: str) -> list[list[float]]:
        """Every chunk's vector, UNPOOLED and L2-normalized -- what a client needs in order to
        index chunks separately, so a query can match the best chunk directly instead of a blur of
        all of them. This is the shape EXP-010 concluded is the real fix for long documents (and
        which pooling, measured there, is not)."""
        body = self.tok.encode_body(text)
        win = SEQ_LEN - 2
        out = []
        for i in range(0, max(len(body), 1), win):
            v = np.asarray(self._embed_ids([self.tok.cls_id, *body[i:i + win], self.tok.sep_id]),
                           dtype=np.float32)
            v /= np.linalg.norm(v) + 1e-12
            out.append([float(x) for x in v])
        return out


def make_handler(engine: Engine):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # keep the server quiet
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
                                 "backend": "Core AI, ANE", "dim": 384,
                                 "seq_len": SEQ_LEN, "chunk": CHUNK, "pool": POOL})
            elif self.path == "/v1/models":
                self._send(200, {"object": "list", "data": [
                    {"id": engine.model_name, "object": "model", "owned_by": "local",
                     "created": 0}]})
            else:
                self._send(404, {"error": {"message": f"no route {self.path}"}})

        def do_POST(self) -> None:
            if self.path not in ("/v1/embeddings", "/v1/chunk_embeddings"):
                self._send(404, {"error": {"message": f"no route {self.path}"}})
                return
            try:
                n = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(n) or b"{}")
            except Exception as exc:  # noqa: BLE001
                self._send(400, {"error": {"message": f"bad JSON: {exc}"}})
                return

            raw = payload.get("input", payload.get("inputs", ""))
            texts = raw if isinstance(raw, list) else [raw]
            texts = [t if isinstance(t, str) else json.dumps(t) for t in texts]
            if not texts:
                self._send(400, {"error": {"message": "empty input"}})
                return

            try:
                if self.path == "/v1/chunk_embeddings":
                    # one entry per input, each carrying every chunk vector unpooled
                    data = [{"object": "chunk_embeddings", "index": i,
                             "embeddings": engine.chunk_vectors(t)}
                            for i, t in enumerate(texts)]
                else:
                    vectors = [engine.embed_one(t) for t in texts]
                    data = [{"object": "embedding", "index": i, "embedding": v}
                            for i, v in enumerate(vectors)]
            except Exception as exc:  # noqa: BLE001
                self._send(500, {"error": {"message": f"{type(exc).__name__}: {exc}"}})
                return

            self._send(200, {
                "object": "list",
                "data": data,
                "model": payload.get("model", engine.model_name),
                "usage": {"prompt_tokens": 0, "total_tokens": 0},
            })
            engine.maybe_recycle()   # response is flushed; safe to replace the process

    return Handler


def main() -> int:
    global SEQ_LEN
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    ap.add_argument("--tokenizer", type=Path, default=DEFAULT_TOKENIZER)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--model-name", default="granite-embedding-97m")
    ap.add_argument("--restart-every", type=int, default=4000,
                    help="re-exec after N calls: the runtime leaks IOSurfaces (see embed_one)")
    # Any grid the exported bundle uses. The graph is a fixed grid, so this must match the
    # bundle; a sweep needs values beyond the two published ones.
    ap.add_argument("--pool", choices=["max", "mean"], default="max",
                    help="how to combine chunk vectors (default: max)")
    ap.add_argument("--chunk", action="store_true",
                    help="split long bodies into SEQ_LEN-2 windows and max-pool "
                         "(default: truncate at the grid)")
    ap.add_argument("--seq-len", type=int, default=SEQ_LEN,
                    help="the graph grid; MUST match the exported bundle")
    args = ap.parse_args()

    global CHUNK, POOL
    SEQ_LEN = args.seq_len
    CHUNK = args.chunk
    POOL = args.pool

    for p in (args.bundle, args.tokenizer):
        if not p.exists():
            print(f"missing {p}", file=sys.stderr)
            return 2

    print(f"loading {args.bundle.name} (ANE preference) …", flush=True)
    engine = Engine(args.bundle, args.tokenizer, args.model_name,
                    restart_every=args.restart_every)
    v = engine.embed_one("warmup")
    print(f"ready: {len(v)}-dim embeddings on {args.host}:{args.port} "
          f"(grid S={args.seq_len}{', chunked+maxpool' if args.chunk else ', truncate'})", flush=True)

    inherited = os.environ.get("EMBED_INHERIT_FD")
    if inherited:
        # adopted from the previous incarnation: same socket, so no client is refused
        fd = int(inherited)
        sock = socket.fromfd(fd, socket.AF_INET, socket.SOCK_STREAM)
        srv = ThreadingHTTPServer((args.host, args.port), make_handler(engine), bind_and_activate=False)
        srv.socket.close()
        srv.socket = sock
        srv.server_address = sock.getsockname()
        srv.server_activate()
        engine.listen_fd = sock.fileno()
        print(f"adopted inherited listening socket (fd {fd})", flush=True)
    else:
        srv = ThreadingHTTPServer((args.host, args.port), make_handler(engine))
        engine.listen_fd = srv.socket.fileno()
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
