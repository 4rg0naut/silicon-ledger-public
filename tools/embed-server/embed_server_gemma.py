#!/usr/bin/env python3
"""EmbeddingGemma-300m served from its AOT Core AI bundle, on the Neural Engine.

Same /v1/embeddings shape as our Granite server, so the retrieval harnesses can be pointed at it
unchanged. Built to answer one question: EmbeddingGemma leads the zoo's multilingual table on
English and JaQuAD -- does it hold that lead when it runs on the ANE like the rest of our stack?

Bundle facts (from the zoo's repo, NOT gated -- the upstream google/embeddinggemma-300m is):
  * model/embeddinggemma-300m_float32_static.aimodel   -- float32, seq_len 256 (per reference.json)
  * output: L2-normalized 768-d
  * prompts (from reference.json): query "task: search result | query: ",
                                   document "title: none | text: "
  * compiles to FULL ANE residency (1 region, 0 GPU, 0 CPU) -- verified before writing this

usage:
    python tools/embed-server/embed_server_gemma.py --port 8976
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
BUNDLE_DIR = ROOT / "models" / "embeddinggemma-300m" / "model"
AIMODEL = BUNDLE_DIR / "embeddinggemma-300m_float32_static.aimodel"
SEQ_LEN = 256
MODEL_NAME = "embeddinggemma-300m-ane"


class Engine:
    def __init__(self, model_name: str = MODEL_NAME, restart_every: int = 3000,
                 delegate: str = "ane") -> None:
        from tokenizers import Tokenizer
        from coreai.runtime import AIModel, NDArray, ComputeUnitKind, SpecializationOptions

        self.NDArray = NDArray
        self.model_name = model_name
        self.delegate = delegate
        ref = json.loads((BUNDLE_DIR / "reference.json").read_text())
        self.prompts = ref["prompts"]
        self.seq_len = int(ref.get("seq_len", SEQ_LEN))

        self.tok = Tokenizer.from_file(str(BUNDLE_DIR / "tokenizer" / "tokenizer.json"))
        # The bundle's tokenizer.json ships a PADDING config, so encode("hello") already returns a
        # full 256-id row padded with <pad>. Taking len(ids) as the real length therefore marks every
        # pad as a real token and the graph attends to noise -- measured as a 1.16e-01 cosine error
        # against the bundle's own reference.json. Disable padding and truncation here; we do both
        # ourselves below so `real` means what it says.
        self.tok.no_padding()
        self.tok.no_truncation()
        cfg = json.loads((BUNDLE_DIR / "tokenizer" / "tokenizer_config.json").read_text())
        pad = cfg.get("pad_token") or cfg.get("pad_token_id") or "<pad>"
        try:
            self.pad_id = self.tok.token_to_id(str(pad))
        except Exception:  # noqa: BLE001
            self.pad_id = 0
        if self.pad_id is None:
            self.pad_id = 0

        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        unit = {"ane": ComputeUnitKind.neural_engine(), "gpu": ComputeUnitKind.gpu(),
                "cpu": ComputeUnitKind.cpu()}[delegate]
        opts = SpecializationOptions.from_preferred_compute_unit_kind(unit)
        self.model = self._run(AIModel.load(AIMODEL, specialization_options=opts))
        self.fn = self.model.load_function("main")
        self._calls = 0
        self.restart_every = restart_every
        self.listen_fd = -1
        self._next_recycle = restart_every

    def maybe_recycle(self) -> None:
        """Recycle after the reply is flushed; the listening socket is inherited across the exec.

        Measured: this bundle dies with an MPSCommandBufferImageCache assertion
        ('Released a texture not in current cache frame') after ~6,400 embeddings, which is the
        IOSurface pool again (F-31) -- the runtime exposes no release API, so the process must
        re-exec. Without this, MIRACL-ja (8,000 docs) cannot complete.
        """
        if not self.restart_every or self._calls < self._next_recycle:
            return
        self._next_recycle = self._calls + self.restart_every
        print(f"recycling after {self._calls} calls", flush=True)
        sys.stdout.flush()
        os.environ["GEMMA_INHERIT_FD"] = str(self.listen_fd)
        os.set_inheritable(self.listen_fd, True)
        os.execv(sys.executable, [sys.executable, *sys.argv])

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()

    def chunk_vectors(self, text: str, kind: str = "document") -> list[list[float]]:
        """Unpooled per-chunk vectors, same contract as the Granite server's /v1/chunk_embeddings,
        so bench/rerank_retrieval.py can be pointed at either embedder unchanged."""
        prefix = self.prompts.get("query" if kind == "query" else "document", "")
        ids = self.tok.encode(prefix + text, add_special_tokens=True).ids
        win = self.seq_len - 2
        out = []
        for i in range(0, max(len(ids), 1), win):
            piece = ids[i:i + win]
            real = len(piece)
            padded = piece + [self.pad_id] * (self.seq_len - real)
            mask = [1] * real + [0] * (self.seq_len - real)
            o = self._run(self.fn({
                "input_ids": self.NDArray(np.asarray([padded], dtype=np.int32)),
                "attention_mask": self.NDArray(np.asarray([mask], dtype=np.int32)),
            }))
            v = o["embedding"].numpy().reshape(-1).astype(np.float32)
            del o
            n = float(np.linalg.norm(v)) or 1.0
            out.append([float(x) for x in (v / n)])
            self._calls += 1
        return out

    def embed(self, text: str, kind: str = "document") -> list[float]:
        prefix = self.prompts.get("query" if kind == "query" else "document", "")
        ids = self.tok.encode(prefix + text, add_special_tokens=True).ids[: self.seq_len]
        real = len(ids)
        padded = ids + [self.pad_id] * (self.seq_len - real)
        mask = [1] * real + [0] * (self.seq_len - real)
        out = self._run(self.fn({
            "input_ids": self.NDArray(np.asarray([padded], dtype=np.int32)),
            "attention_mask": self.NDArray(np.asarray([mask], dtype=np.int32)),
        }))
        vec = out["embedding"].numpy().reshape(-1)
        del out
        self._calls += 1
        if self._calls % 500 == 0:
            gc.collect()
        return [float(x) for x in vec]


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
                                 "backend": f"Core AI, {engine.delegate.upper()} (AOT)", "dim": 768,
                                 "seq_len": engine.seq_len})
            else:
                self._send(404, {"error": {"message": f"no route {self.path}"}})

        def do_POST(self) -> None:
            if self.path not in ("/v1/embeddings", "/v1/chunk_embeddings"):
                self._send(404, {"error": {"message": f"no route {self.path}"}})
                return
            n = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(n) or b"{}")
            raw = payload.get("input", "")
            texts = raw if isinstance(raw, list) else [raw]
            kind = payload.get("kind", "document")
            if self.path == "/v1/chunk_embeddings":
                data = [{"object": "chunk_embeddings", "index": i,
                         "embeddings": engine.chunk_vectors(
                             t if isinstance(t, str) else json.dumps(t), kind)}
                        for i, t in enumerate(texts)]
            else:
                vectors = [engine.embed(t if isinstance(t, str) else json.dumps(t), kind)
                           for t in texts]
                data = [{"object": "embedding", "index": i, "embedding": v}
                        for i, v in enumerate(vectors)]
            self._send(200, {"object": "list", "data": data,
                             "model": payload.get("model", engine.model_name)})
            engine.maybe_recycle()

    return Handler


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8976)
    ap.add_argument("--delegate", choices=["ane", "gpu", "cpu"], default="ane",
                    help="this bundle is fp32; the model card says fp16 is unsupported for its "
                         "activations, and fp32 on the ANE crashes MPSGraph under load (F-35)")
    ap.add_argument("--restart-every", type=int, default=3000,
                    help="re-exec after N calls: this bundle dies with an MPSCommandBufferImageCache "
                         "assertion after ~6400 embeddings (the F-31 IOSurface pool)")
    args = ap.parse_args()
    engine = Engine(restart_every=args.restart_every, delegate=args.delegate)
    inherited = os.environ.pop("GEMMA_INHERIT_FD", None)
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
    print(f"ready: EmbeddingGemma-300m on the ANE at {args.host}:{args.port} "
          f"(seq_len {engine.seq_len}, dim 768, pad {engine.pad_id})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
