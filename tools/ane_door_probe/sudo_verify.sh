#!/bin/sh
# EXP-035 C-85 sudo kernel-log decider — run from a human terminal:
#   sudo /data/OpenFox/dev_m5max_re/silicon-ledger/tools/ane_door_probe/sudo_verify.sh
# Decides Gate-A ([[core+0x10]+0x88] pre-args reject) vs handle key-gate miss:
#   "Could not find program for handle" PRESENT => Gate-A passed, key gate failed
#   ABSENT                                       => died at Gate-A (client-state word)
# Measured 2026-10-23: macOS 27 log config has no private_data key anymore (valid:
# level/persist/stream/signpost*); bare `log` hits the zsh builtin -> /usr/bin/log;
# default stream showed 0 ANE lines during probe8 (driver logs below default level),
# hence the explicit subsystem level:debug + log show fallback.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
D="$HERE/../../results/EXP-035-chaining-blob/raw"
mkdir -p "$D"
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$D/sudo_kernel_log_$TS.txt"
/usr/bin/log config --subsystem com.apple.driver.AppleH16ANEInterface --mode level:debug,persist:debug || echo "WARN: H16 subsystem config failed — continuing"
/usr/bin/log config --subsystem com.apple.driver.AppleH11ANEInterface --mode level:debug,persist:debug 2>/dev/null || true
/usr/bin/log stream --style compact --predicate 'process == "kernel" AND (subsystem == "com.apple.driver.AppleH16ANEInterface" OR eventMessage CONTAINS[c] "ANE" OR eventMessage CONTAINS[c] "program handle")' > "$OUT" 2>&1 &
LOGPID=$!
sleep 2
cd "$HERE"   # probe8_replay reads baseline.mil from CWD (measured: root run from
             # another dir dies "no baseline.mil" BEFORE issuing any door call)
[ -f baseline.mil ] || { kill "$LOGPID" 2>/dev/null; echo "FATAL: $HERE/baseline.mil missing"; exit 1; }
"$HERE/probe8_replay" > "$D/sudo_probe8_$TS.jsonl" 2> "$D/sudo_probe8_$TS.stderr" || true
sleep 2
kill "$LOGPID" 2>/dev/null || true
wait "$LOGPID" 2>/dev/null || true
/usr/bin/log show --last 2m --style compact --predicate 'process == "kernel" AND (subsystem == "com.apple.driver.AppleH16ANEInterface" OR eventMessage CONTAINS[c] "program handle")' > "$D/sudo_logshow_$TS.txt" 2>&1 || true
chmod a+w "$D/sudo_kernel_log_$TS.txt" "$D/sudo_probe8_$TS.jsonl" "$D/sudo_probe8_$TS.stderr" "$D/sudo_logshow_$TS.txt" 2>/dev/null || true
echo "captured: $OUT"
echo "=== probe8 witness (live handle + arm counts must be here, else the run died):"
head -3 "$D/sudo_probe8_$TS.stderr"
echo "=== arm kr summary:"
grep -c '"kr":"0xe00002c2"' "$D/sudo_probe8_$TS.jsonl" 2>/dev/null || true
echo "=== handle-gate lines:"
grep -ihE "Could not find program|Found client|program handle|chainingPrepare" "$OUT" "$D/sudo_logshow_$TS.txt" | head -40 || true
echo "=== (if empty above, check full files: $OUT + $D/sudo_logshow_$TS.txt)"
echo "restore defaults: sudo /usr/bin/log config --subsystem com.apple.driver.AppleH16ANEInterface --mode level:default,persist:default"
