#!/bin/zsh
# P2 Lane-A sudo capture — user-run one-shot, ~30 s total.
# Captures (1) aned file activity around a public Core ML MiniLM load+predict,
# (2) aned cache/clone inventory after the load,
# (3) dtrace census on our own probe: which AppleNeuralEngine/Espresso methods the
#     public E5 route actually calls (the Path-B producer recipe),
# (4) fs_usage of our _ANEClient pathb failure for comparison.
# usage:  sudo /tmp/p2_sudo_capture.sh
set -u
LOG=/tmp/p2_sudo_capture.txt
: > "$LOG"
H=/Volumes/data/OpenFox/dev_m5max_re/silicon-ledger/results/EXP-025-ane-gpu-sync/harness

echo "== [1] fs_usage aned (12s) during public load ==" | tee -a "$LOG"
fs_usage -w -f filesys -t 12 aned 2>/dev/null >> "$LOG" &
FSU=$!; sleep 0.5
/tmp/mlc_load /tmp/fresh128.mlmodelc >> "$LOG" 2>&1
wait $FSU 2>/dev/null || true

echo "== [2] aned cache/clone inventory ==" | tee -a "$LOG"
find /Library/Caches/com.apple.aned -maxdepth 4 -mmin -5 -exec ls -lad {} + >> "$LOG" 2>&1

echo "== [3] dtrace census on probe (E5 route) ==" | tee -a "$LOG"
PROBE_LOOPS=200 /tmp/mlc_load /tmp/fresh128.mlmodelc >> "$LOG" 2>&1 &
INF=$!; sleep 1
dtrace -p $INF -s /tmp/p2_census.d > /tmp/p2_census_out.txt 2>&1 &
DP=$!
# wait for inferior to finish its loops (no ANE stop flag exists; loops self-terminate ~12s)
for i in $(seq 1 40); do kill -0 $INF 2>/dev/null || break; sleep 1; done
sleep 2; wait $DP 2>/dev/null || true
kill $INF 2>/dev/null
echo "census -> /tmp/p2_census_out.txt ($(wc -l < /tmp/p2_census_out.txt) lines)"

echo "== [4] fs_usage our _ANEClient pathb failure ==" | tee -a "$LOG"
fs_usage -w -f filesys -t 5 aned 2>/dev/null >> "$LOG" &
FSU2=$!; sleep 0.3
(cd "$H" && PATHB_DIR=/tmp/fresh128.mlmodelc ./ane_sync_harness pathb >> "$LOG" 2>&1)
wait $FSU2 2>/dev/null || true

echo "done: $LOG ($(wc -l < "$LOG") lines), census /tmp/p2_census_out.txt"
