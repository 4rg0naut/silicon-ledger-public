#!/bin/zsh
# T8 setup: build the M5 Python/export stack from zero (EXP-023 prep).
# Nothing here measures latency; it must FINISH by ~02:45 so the 03:17 capture runs idle.
set -u
L=/Volumes/data/OpenFox/dev_m5max_re/silicon-ledger
LOG=$L/work/t8-setup.log
mkdir -p "$L/work" "$L/repos" "$L/models"
exec >>"$LOG" 2>&1
echo "=== t8_setup start $(date -u) ==="

if ! command -v uv >/dev/null; then
  echo "[1/5] installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh || { echo "FAIL uv"; exit 1; }
fi
export PATH="$HOME/.local/bin:$PATH"
uv --version

cd "$L"
echo "[2/5] venv python 3.13 (coreai-core wheels exist for cp313; coreai-models 0.1.0 wheel is pure-python)"
uv venv .venv --python 3.13 --clear --seed || { echo "FAIL venv"; exit 1; }

echo "[3/5] install coreai-torch stack, then coreai-models wheel past its metadata pin"
VIRTUAL_ENV="$L/.venv" uv pip install "numpy<2.4" transformers huggingface_hub coreai-torch==0.4.2 || { echo "FAIL pip"; exit 1; }
mkdir -p /tmp/coreai-models-wheel && cd /tmp/coreai-models-wheel
curl -sL -o coreai_models-0.1.0-py3-none-any.whl https://files.pythonhosted.org/packages/source/c/coreai-models/coreai_models-0.1.0.tar.gz >/dev/null
curl -s https://pypi.org/pypi/coreai-models/0.1.0/json | python3 -c "
import json,sys,urllib.request
d=json.load(sys.stdin)
url=[u['url'] for u in d['urls'] if u['packagetype']=='bdist_wheel'][0]
urllib.request.urlretrieve(url,'coreai_models-0.1.0-py3-none-any.whl')
print('wheel fetched:',url)
" || { echo "FAIL wheel fetch"; exit 1; }
VIRTUAL_ENV="$L/.venv" "$L/.venv/bin/python" -m pip install --no-deps --ignore-requires-python coreai_models-0.1.0-py3-none-any.whl || { echo "FAIL wheel install"; exit 1; }
"$L/.venv/bin/python" -c "import coreai_models, torch, transformers; print('coreai_models OK', 'torch', torch.__version__)" || { echo "FAIL import coreai_models — export script will need the kit checkout path"; }

echo "[4/5] coreai-kit checkout skipped (PyPI coreai-models provides coreai_models; apple/coreai-kit is not public)"

echo "[5/5] HF checkpoint Qwen3-Reranker-0.6B"
"$L/.venv/bin/hf" download Qwen/Qwen3-Reranker-0.6B --local-dir "$L/models/qwen3-reranker-hf" || { echo "FAIL download"; exit 1; }

du -sh "$L/models/qwen3-reranker-hf"
echo "=== t8_setup DONE $(date -u) ==="
