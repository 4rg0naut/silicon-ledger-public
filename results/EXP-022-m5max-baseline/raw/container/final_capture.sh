#!/bin/zsh
# EXP-022 FINAL clean capture — M5 Max (Mac17,14), fingerprint bda452aabd60bf26.
#
# Runs scheduled (cron) in a fully quiet window: the OpenFox/oMLX agent (local
# Qwen3.8-27B, ~30 GB RSS) is stopped, so there is no in-session GPU inference
# load AND no 30 GB resident-memory confounder. Every step runs from the bench
# workspace CWD (the 16:05 capture ran `bench all` from the session workdir and
# lost S4 — fixed here).
#
# Telemetry stack (see findings-so-far.md + SiliconScope, MIT, v4.4.0):
#   ssample      SiliconScopeCore harness: PMP0 "DCS BW" per-engine bandwidth lanes
#                (ANE lane is THE ANE-activity signal on M5 Max: 156 GB moved
#                during bench ane vs 0 idle) + batched-regime-aware energy rails
#   enginemon    raw Apple libIOReport dump (--all): secondary; on M5 all ANE
#                energy/interrupt channels are dead (zero even under confirmed
#                ANE load) — kept as the raw negative + for the record
#   xctrace      Core AI template, ane-hw-intervals (expected 0: Core AI blind
#                spot, now artifact-confirmed by AOT 0-region bundles)
#   coreai-build AOT region counts, h17g + h16g targets
#
# Outputs everything under exp022-raw/final-<UTC-ts>/ and never deletes anything.
set -u
export PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer

RAW=/Volumes/data/OpenFox/dev_m5max_re/exp022-raw
TS=$(date -u +%Y-%m-%dT%H-%M-%SZ)
OUT=$RAW/final-$TS
BENCH="/Users/<user>/Library/Application Support/openfox/workspaces/dev_m5max_re/silicon-ledger-publish"
BIN=$BENCH/.build/release/bench
EXAMPLE=$BENCH/examples/2026-09-26T02-14-33Z-bda452aabd60bf26.json
ENG=$RAW/bin/enginemon
SSAMPLE=$RAW/bin/ssample
LEDGER=/Volumes/data/OpenFox/dev_m5max_re/silicon-ledger

[ -x "$BIN" ]     || { echo "FATAL: bench missing: $BIN" | tee "$RAW/cron.log"; exit 1; }
[ -x "$SSAMPLE" ] || { echo "FATAL: ssample missing: $SSSAMPLE" | tee "$RAW/cron.log"; exit 1; }
[ -x "$ENG" ]     || { echo "FATAL: enginemon missing: $ENG" | tee "$RAW/cron.log"; exit 1; }
mkdir -p "$OUT"
echo "start $TS -> $OUT" >> "$RAW/cron.log"
cd "$BENCH"

{
  echo "== env @ $(date -u) =="
  uptime
  sw_vers
  sysctl -n hw.model
  echo "loadavg(1min): $(/usr/bin/python3 -c 'import os; print(os.getloadavg()[0])')"
  ps aux -m | head -25
  memory_pressure 2>/dev/null | head -12
} > "$OUT/env.txt"

# idle guard: two consecutive quiet checks, 15 min apart, max 2 h
load1() { /usr/bin/python3 -c 'import os; print(os.getloadavg()[0])'; }
idle_ok() { /usr/bin/python3 -c 'import os,sys; sys.exit(0 if os.getloadavg()[0] < 4.0 else 1)'; }
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
tools/stability_run.sh exp022_final > "$OUT/stability.log" 2>&1
STAB_RC=$?
echo "stability rc=$STAB_RC" >> "$RAW/cron.log"
cp /tmp/exp022_final_good.txt "$OUT/good-runs.txt" 2>/dev/null
for f in /tmp/exp022_final_*.log(N); do cp "$f" "$OUT/"; done

# 2) full suite (CWD = bench workspace, so models/coreai resolves and S4 runs)
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

# 4) ssample windows (primary M5 telemetry: PMP0 DCS BW lanes + energy)
"$SSAMPLE" --duration 30 > "$OUT/ssample-idle-control.log" 2>&1
"$SSAMPLE" --duration 300 -- "$BIN" ane > "$OUT/ssample-ane.log" 2>&1
"$SSAMPLE" --duration 300 -- "$BIN" coreai > "$OUT/ssample-coreai.log" 2>&1

# 5) enginemon raw windows (secondary; documents the dead-channel negative)
"$ENG" --all --interval 500 --duration 30 > "$OUT/enginemon-idle-control.log" 2>&1
"$ENG" --all --interval 500 --duration 600 -- "$BIN" ane > "$OUT/enginemon-ane.log" 2>&1
"$ENG" --all --interval 500 --duration 300 -- "$BIN" coreai > "$OUT/enginemon-coreai.log" 2>&1

# 6) xctrace around a fresh Core AI run; then ane-hw-intervals summary
if xctrace list templates > /dev/null 2>&1; then
  ( xctrace record --no-prompt --template 'Core AI' --time-limit 300s \
      --output "$OUT/coreai-ane.trace" --launch -- "$BIN" coreai > "$OUT/xctrace.log" 2>&1 )
  "$LEDGER/bench/ane_report.py" "$OUT/coreai-ane.trace" m5-final-coreai > "$OUT/xctrace-ane-intervals.txt" 2>&1 \
    || echo "ane_report failed" >> "$OUT/xctrace-ane-intervals.txt"
else
  echo "SKIPPED: xctrace unavailable (Xcode license?)" > "$OUT/xctrace-ane-intervals.txt"
fi

# 7) AOT region counts (coreai-build inside the Metal Toolchain MobileAsset mount)
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
