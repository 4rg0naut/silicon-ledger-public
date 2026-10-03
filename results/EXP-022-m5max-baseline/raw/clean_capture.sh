#!/bin/zsh
# EXP-022 clean measurement capture — M5 Max (Mac17,14), fingerprint bda452aabd60bf26
#
# WHY SCHEDULED: the OpenFox agent on this box runs locally via oMLX (Qwen3.8-27B,
# ~30 GB RSS). Every generated token is live GPU work on the machine under test,
# so in-session measurements are contaminated (measured: gpu_copy 379.5 GB/s while
# the agent was lightly active vs 72-91 GB/s while actively generating). This script
# runs via cron in a quiet window (default 02:00) and only proceeds when the 1-min
# load average is < 4.0 for two consecutive checks.
#
# Outputs everything under exp022-raw/cron-<UTC-ts>/ and never deletes anything.
set -u
export PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer

RAW=/Volumes/data/OpenFox/dev_m5max_re/exp022-raw
TS=$(date -u +%Y-%m-%dT%H-%M-%SZ)
OUT=$RAW/cron-$TS
BENCH="/Users/<user>/Library/Application Support/openfox/workspaces/dev_m5max_re/silicon-ledger-publish"
BIN=$BENCH/.build/release/bench
EXAMPLE=$BENCH/examples/2026-09-26T02-14-33Z-bda452aabd60bf26.json
ENG=$RAW/bin/enginemon
LEDGER=/Volumes/data/OpenFox/dev_m5max_re/silicon-ledger

[ -x "$BIN" ] || { echo "FATAL: bench binary missing: $BIN" | tee "$RAW/cron.log"; exit 1; }
[ -x "$ENG" ] || { echo "FATAL: enginemon missing: $ENG" | tee "$RAW/cron.log"; exit 1; }
mkdir -p "$OUT"
echo "start $TS -> $OUT" >> "$RAW/cron.log"

{
  echo "== env @ $(date -u) =="
  uptime
  sw_vers
  sysctl -n hw.model
  echo "loadavg(1min): $(/usr/bin/python3 -c 'import os; print(os.getloadavg()[0])')"
  ps aux -m | head -25
  memory_pressure 2>/dev/null | head -12
} > "$OUT/env.txt"

load1() { /usr/bin/python3 -c 'import os; print(os.getloadavg()[0])'; }
idle_ok() { /usr/bin/python3 -c 'import os,sys; sys.exit(0 if os.getloadavg()[0] < 4.0 else 1)'; }

# idle guard: two consecutive quiet checks, 15 min apart, max 2 h
QUIET=0
ATTEMPT=0
while :; do
  if idle_ok; then
    QUIET=$((QUIET+1))
    echo "$(date -u) idle check $ATTEMPT: load1=$(load1) quiet=$QUIET" >> "$OUT/env.txt"
    (( QUIET >= 2 )) && break
  else
    QUIET=0
    echo "$(date -u) idle check $ATTEMPT: load1=$(load1) NOT idle" >> "$OUT/env.txt"
  fi
  ATTEMPT=$((ATTEMPT+1))
  (( ATTEMPT > 9 )) && { echo "ABORT: machine not idle after 2h" | tee -a "$RAW/cron.log"; exit 1; }
  sleep 900
done

# 0) probe: fingerprint + ANE reachability flags
"$BIN" probe > "$OUT/probe.txt" 2>&1

# 1) official stability series: 3 GOOD bench memory runs + check_stability --suite=s1
(cd "$BENCH" && tools/stability_run.sh exp022_clean) > "$OUT/stability.log" 2>&1
STAB_RC=$?
echo "stability rc=$STAB_RC" >> "$RAW/cron.log"
cp /tmp/exp022_clean_good.txt "$OUT/good-runs.txt" 2>/dev/null
for f in /tmp/exp022_clean_*.log(N); do cp "$f" "$OUT/"; done

# 2) full suite, warm after the stability runs (R9: run warm, back-to-back)
"$BIN" all > "$OUT/bench-all.log" 2>&1
REPORT=$(sed -n 's/^report: //p' "$OUT/bench-all.log" | tail -1)
if [ -n "$REPORT" ] && [ -f "$REPORT" ]; then
  cp "$REPORT" "$OUT/report.json"
  echo "report: $REPORT" >> "$RAW/cron.log"
  # 3) diff vs the reference record
  "$BIN" diff "$EXAMPLE" "$REPORT" > "$OUT/diff-vs-example.txt" 2>&1
else
  echo "WARN: no report line in bench-all.log" >> "$RAW/cron.log"
fi

# 4) enginemon idle control (baseline: which channels move with no workload)
"$ENG" --all --interval 500 --duration 30 > "$OUT/enginemon-idle-control.log" 2>&1

# 5) enginemon while ANE raw runs.
# M5 channel map differs from M4: no AMC Stats group, no `ane 0` subgroup (only
# `dart-ane0 0`), no PMP. Read the per-channel table, not the M4-style summary:
# expect `dart-ane0 0` handler counts and/or `ANE0` energy delta to move.
"$ENG" --all --interval 500 --duration 600 -- "$BIN" ane > "$OUT/enginemon-ane.log" 2>&1

# 6) enginemon while Core AI runs (R10: expect ~0 ANE movement, high GPU energy)
"$ENG" --all --interval 500 --duration 300 -- "$BIN" coreai > "$OUT/enginemon-coreai.log" 2>&1

# 7) xctrace around a fresh Core AI run; then ane-hw-intervals summary
if xctrace list templates > /dev/null 2>&1; then
  ( cd "$OUT" && xctrace record --no-prompt --template 'Core AI' --time-limit 300s \
      --output coreai-ane.trace -- "$BIN" coreai > xctrace-record.log 2>&1 )
  "$LEDGER/bench/ane_report.py" "$OUT/coreai-ane.trace" m5-coreai > "$OUT/xctrace-ane-intervals.txt" 2>&1 \
    || echo "ane_report failed" >> "$OUT/xctrace-ane-intervals.txt"
else
  echo "SKIPPED: xctrace unavailable (Xcode license not accepted? run: sudo xcodebuild -license)" \
    > "$OUT/xctrace-ane-intervals.txt"
fi

# 7) AOT region counts. Note: Xcode's own `aimodelc` refuses to run even with the
# Metal Toolchain component installed; the working compiler is `coreai-build` inside
# the MobileAsset mount (per-machine path suffix -> resolve by glob).
CB=$(ls -d /private/var/run/com.apple.security.cryptexd/mnt/com.apple.MobileAsset.MetalToolchain-*/Metal.xctoolchain/usr/bin/coreai-build 2>/dev/null | head -1)
mkdir -p "$OUT/aot"
: > "$OUT/aot.log"
if [ -n "$CB" ] && [ -x "$CB" ]; then
  for arch in h17g h16g; do
    for model in matmul deep_fp16 deep_int8; do
      if "$CB" compile "$BENCH/models/coreai/$model.aimodel" \
          --output "$OUT/aot/$arch-$model" \
          --preferred-compute neural-engine --architecture "$arch" >> "$OUT/aot.log" 2>&1; then
        N=$(find "$OUT/aot/$arch-$model" -name '*ANE_region*' 2>/dev/null | wc -l | tr -d ' ')
        echo "AOT $arch/$model: regions=$N" >> "$OUT/aot.log"
      else
        echo "AOT $arch/$model: FAILED (see aot.log)" >> "$OUT/aot.log"
      fi
    done
  done
else
  echo "SKIPPED: coreai-build not found (Metal Toolchain component missing?)" > "$OUT/aot.log"
fi

echo "DONE $TS -> $OUT" >> "$RAW/cron.log"
echo "done $TS" >> "$OUT/env.txt"
