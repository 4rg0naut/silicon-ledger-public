#!/bin/zsh
# C3 PRIMARY channel runner — requires sudo (dtrace needs root; pid provider on our
# own user-built harness is NOT SIP-denied, unlike aned).  Takes a few minutes.
#   usage: sudo ./harness/trace_primary.sh
set -u
cd "$(dirname "$0")/.."
OUT=results/dtrace_primary.txt
{
  echo "# dtrace PRIMARY channel — own harness (user-built, pid-provider allowed)"
  echo "# run by $(id -un) at $(date '+%F %T %z')"
  sw_vers | sed 's/^/# /'
  echo "# hw.model=$(sysctl -n hw.model)"
  echo
  echo "## run 1: latency mode (compile + 5-batch eval window)"
  echo '# dtrace -F -c "harness/ane_sync_harness latency" -s harness/ane_primary.d'
  dtrace -F -c 'harness/ane_sync_harness latency' -s harness/ane_primary.d 2>&1
  echo
  echo "## run 2: porttest mode (MTLSharedEvent <-> IOSurfaceSharedEvent bridge window)"
  echo '# dtrace -F -c "harness/ane_sync_harness porttest" -s harness/ane_primary.d'
  dtrace -F -c 'harness/ane_sync_harness porttest' -s harness/ane_primary.d 2>&1
  echo
  echo "## objc-provider probe enumeration (best-effort; provider may be SIP-gated)"
  echo '# dtrace -c harness/ane_sync_harness porttest -l -n "objc\$target"'
  dtrace -c 'harness/ane_sync_harness porttest' -l -n 'objc$target' 2>&1 | head -40
  echo
  echo "## objc-provider attempt 2: exact class _ANESharedEvents"
  dtrace -F -c 'harness/ane_sync_harness porttest' \
    -n 'objc$target:_ANESharedEvents::entry { printf("objc_entry %s %s\n", probemod, probefunc); }' 2>&1 | head -20
  echo
  echo "## objc-provider attempt 3: -[_ANE*] method entries"
  dtrace -F -c 'harness/ane_sync_harness porttest' \
    -n 'objc$target:_ANE*::entry { printf("objc_entry %s %s\n", probemod, probefunc); }' 2>&1
} > "$OUT" 2>&1
echo "wrote $OUT"
tail -5 "$OUT"
