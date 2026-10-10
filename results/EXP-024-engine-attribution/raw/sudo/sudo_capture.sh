#!/bin/zsh
# EXP-024 sudo rail capture — run as:  sudo zsh /Volumes/data/OpenFox/dev_m5max_re/exp024-raw/sudo/sudo_capture.sh
set -u
OUT=/Volumes/data/OpenFox/dev_m5max_re/exp024-raw/sudo
LEDGER=/Volumes/data/OpenFox/dev_m5max_re/silicon-ledger
WS="/Users/<user>/Library/Application Support/openfox/workspaces/dev_m5max_re/silicon-ledger-publish"
EM=$LEDGER/tools/enginemon/enginemon
mkdir -p "$OUT"
export HF_HOME=/Users/<user>/.cache/huggingface
export HF_HUB_OFFLINE=1
{ echo "== date"; date -u +%FT%TZ; echo "== euid"; id -u; } > "$OUT/meta.txt" 2>&1
# 1. Privileged IOReport surface test (does AMC Stats unlock under root?)
"$EM" --list > "$OUT/eng_list_priv.txt" 2>&1
echo "AMC lines privileged: $(grep -c 'AMC Stats' "$OUT/eng_list_priv.txt")" >> "$OUT/meta.txt"
# 2. Power A/B (Core ML MiniLM ALL vs CPU_ONLY rails; coremltools-free path)
cd "$LEDGER" || exit 1
.venv-conv/bin/python bench/power_mlcore.py --seconds 20 > "$OUT/power_mlcore_run.log" 2>&1
cp bench/power_ALL.txt "$OUT/power_ALL.txt" 2>/dev/null
cp bench/power_CPU_ONLY.txt "$OUT/power_CPU_ONLY.txt" 2>/dev/null
# 3. Core AI power attribution (granite-runner, three compute-unit lanes)
if [ -x tools/granite-runner/.build/release/granite-runner ]; then
  sudo .venv-conv/bin/python bench/power_coreai.py --bundle /Volumes/HUB/models/silicon-ledger-studio/work/exports/granite-rebake-p3/granite97m_fp16_s128.aimodel --iters 800 > "$OUT/power_coreai_run.log" 2>&1
fi
# 4. ANE direct-path under privileged enginemon (does AMC/handlers move under sudo?)
cd "$WS" && "$EM" --interval 500 --duration 90 --json -- .build/release/bench ane --subset dispatch,scaling --iters 80 > "$OUT/cal_ane_priv.jsonl" 2>&1
# 5. tensorops arm under privileged enginemon
cd "$WS" && "$EM" --interval 500 --duration 40 --json -- .build/release/bench gemm --paths tensorops --sizes 4096 --iters 80 > "$OUT/cal_tensorops_priv.jsonl" 2>&1
# 6. #8 stage 4: privileged powermetrics gpu_power, tensorops load vs idle
# NOTE 2026-10-06: original used `-t 15000` (SECONDS — never ended within the
# window; had to be interrupted, truncating raw dumps at 64 KiB flush boundary).
# Fixed to bounded sample counts. NOTE 2: full-size tensorops arms no-op on this
# toolchain (R8) — this arm needs a valid probe before its numbers mean anything.
cd "$WS"
.build/release/bench gemm --paths tensorops --sizes 4096 --iters 500 > "$OUT/stage4_load.log" 2>&1 &
LOADPID=$!
sleep 4
powermetrics --samplers gpu_power -i 500 -n 60 > "$OUT/powermetrics_gpu_tensorops.txt" 2>&1
kill $LOADPID 2>/dev/null
wait $LOADPID 2>/dev/null
powermetrics --samplers gpu_power -i 500 -n 20 > "$OUT/powermetrics_gpu_idle.txt" 2>&1
echo SUDO_CAPTURE_DONE
