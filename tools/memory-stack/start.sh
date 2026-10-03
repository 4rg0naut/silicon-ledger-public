#!/usr/bin/env bash
# start.sh — bring up the fully-local memory stack and print what to export.
#
#   1. the ANE embedding server   : Granite-Embedding-97M, 384-d, /v1/embeddings   (port 8799)
#   2. the on-device LLM server   : Apple Foundation Models, /v1/chat/completions   (port 1976)
#
# Both are loopback-only. Nothing leaves the machine and no API key is needed.
#
# usage:  tools/memory-stack/start.sh          # start (idempotent) and print the exports
#         tools/memory-stack/start.sh --stop   # stop both
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
EMBED_PORT=8799
LLM_PORT=1976
LOG_DIR="$ROOT/work/memory-stack"
mkdir -p "$LOG_DIR"

alive() { curl -s --max-time 2 "http://127.0.0.1:$1/health" >/dev/null 2>&1; }

if [ "${1:-}" = "--stop" ]; then
  for p in "$LLM_PORT" "$EMBED_PORT"; do
    pid=$(lsof -ti tcp:"$p" 2>/dev/null | head -1 || true)
    [ -n "$pid" ] && kill "$pid" && echo "  stopped :$p (pid $pid)"
  done
  exit 0
fi

# ---- 1. embedding server (ANE) ------------------------------------------------
if alive "$EMBED_PORT"; then
  echo "  embedding server already up on :$EMBED_PORT"
else
  echo "  starting embedding server on :$EMBED_PORT …"
  nohup "$ROOT/.venv/bin/python" "$ROOT/tools/embed-server/embed_server.py" --port "$EMBED_PORT" \
    >"$LOG_DIR/embed.log" 2>&1 &
  for _ in $(seq 1 60); do alive "$EMBED_PORT" && break; sleep 1; done
  alive "$EMBED_PORT" || { echo "  FAILED — see $LOG_DIR/embed.log"; exit 1; }
  echo "  embedding server up (ANE)"
fi

# ---- 2. on-device LLM server --------------------------------------------------
if alive "$LLM_PORT"; then
  echo "  LLM server already up on :$LLM_PORT"
else
  echo "  starting fm serve on :$LLM_PORT …"
  nohup fm serve --port "$LLM_PORT" >"$LOG_DIR/fm.log" 2>&1 &
  for _ in $(seq 1 40); do alive "$LLM_PORT" && break; sleep 1; done
  # fm serve exposes /health; fall back to the models route if that ever changes
  if ! alive "$LLM_PORT"; then
    curl -s --max-time 2 "http://127.0.0.1:$LLM_PORT/v1/models" >/dev/null 2>&1 \
      || { echo "  FAILED — see $LOG_DIR/fm.log"; exit 1; }
  fi
  echo "  fm serve up (Apple Foundation Models)"
fi

# ---- what the memory engine needs ---------------------------------------------
cat <<EOF

Both backends are up. For the shell that runs mnemopi:

  export MNEMOPI_DATA_DIR=$ROOT/work/mnemopi-ane
  export MNEMOPI_EMBEDDING_API_URL=http://127.0.0.1:$EMBED_PORT/v1
  export MNEMOPI_EMBEDDING_MODEL=granite-embedding-97m
  export MNEMOPI_LLM_ENABLED=1
  export MNEMOPI_LLM_BASE_URL=http://127.0.0.1:$LLM_PORT/v1
  export MNEMOPI_LLM_MODEL=system

Note: the LLM is gated by BeamMemory's \`localLlmEnabled\` (default false, no env override), so the
CLI alone cannot use it — the host must construct the engine with
\`config: { localLlmEnabled: true }\`. Embeddings work from the CLI as-is.

Logs: $LOG_DIR/{embed,fm}.log
EOF
