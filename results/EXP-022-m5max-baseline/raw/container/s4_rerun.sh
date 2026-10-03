#!/bin/zsh
# One-shot S4 re-run: the 16:37 clean capture ran `bench all` from the session
# workdir (not the bench workspace), so models/coreai/ was not found and S4
# produced "(no runs)". Re-runs S4 with correct CWD + xctrace (needs --launch)
# + enginemon around Core AI.
set -u
export PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
RAW=/Volumes/data/OpenFox/dev_m5max_re/exp022-raw
TS=$(date -u +%Y-%m-%dT%H-%M-%SZ)
OUT=$RAW/s4-rerun-$TS
BENCH="/Users/<user>/Library/Application Support/openfox/workspaces/dev_m5max_re/silicon-ledger-publish"
BIN=$BENCH/.build/release/bench
ENG=$RAW/bin/enginemon
LEDGER=/Volumes/data/OpenFox/dev_m5max_re/silicon-ledger
mkdir -p "$OUT"
cd "$BENCH"

# 1) xctrace Core AI template around bench coreai (--launch required)
xctrace record --no-prompt --template 'Core AI' --time-limit 300s \
  --output "$OUT/coreai-ane.trace" --launch -- "$BIN" coreai > "$OUT/xctrace.log" 2>&1
grep "^report:" "$OUT/xctrace.log" > "$OUT/report-path.txt" 2>/dev/null
$LEDGER/bench/ane_report.py "$OUT/coreai-ane.trace" m5-coreai-s4rerun > "$OUT/xctrace-ane-intervals.txt" 2>&1 \
  || echo "ane_report failed" >> "$OUT/xctrace-ane-intervals.txt"

# 2) enginemon around a fresh bench coreai
"$ENG" --all --interval 500 --duration 300 -- "$BIN" coreai > "$OUT/enginemon-coreai.log" 2>&1

echo "done $TS -> $OUT" >> "$RAW/cron.log"
