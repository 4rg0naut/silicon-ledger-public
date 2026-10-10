#!/bin/zsh
# C3 PRIMARY channel, run 3 — -[_ANE*] method entries via pid provider.
# dtrace -c failed ("pid$target:AppleNeuralEngine::entry does not match any probes")
# because with -c probes are enabled pre-main, before the harness dlopens
# AppleNeuralEngine. Here the inferior is already running (ANE mapped) when we attach.
# Requires sudo. usage: sudo ./harness/trace_ane_attach.sh
set -u
cd "$(dirname "$0")/.."
OUT=results/dtrace_ane_methods.txt
ANE_STOP2=1 ANE_REPS=40 harness/ane_sync_harness latency >/tmp/ane_attach_inferior.log 2>&1 &
INF=$!
sleep 1   # inferior is long-lived (~10s of ANE eval dispatch); attach mid-run
{
  echo "# pid-attached dtrace on running own-harness (inferior pid $INF)"
  echo "# run at $(date '+%F %T %z'), $(sw_vers -productVersion) $(sysctl -n hw.model)"
  echo '# dtrace -p PID -s harness/ane_ane_methods.d; inferior = ANE_STOP2=1 ANE_REPS=40 latency mode'
  echo '# (STOP2 skips the events phase whose PathA crash (F11) kills full latency mode in ~100ms)'
  dtrace -p $INF -s harness/ane_ane_methods.d 2>&1 &
  DPID=$!
  sleep 10
  kill $INF 2>/dev/null      # inferior exit -> dtrace detaches and flushes END aggregations
  wait $DPID
} > "$OUT" 2>&1
kill $INF 2>/dev/null
echo "wrote $OUT"
grep -c "ANE" "$OUT"
