#!/bin/zsh
# EXP-026 K4 v8 sudo capture (user-run): ANE-compiling trigger via the EXP-013
# reranker JIT lane (AN-POS-proven to fire ANE work on this Studio), no fs_usage
# (ktrace device is contended by another session) — poll every aned sandbox in
# /private/var/folders instead and copy NEW files as they appear.
#   sudo zsh results/EXP-026-ane-kitchen/harness/p2b_sudo_capture_v8.sh   (~150s)
set -u
OUT=/tmp/p2b_capture_v8
[[ -d $OUT ]] && mv $OUT $OUT.prev.$(date +%s)
mkdir -p $OUT

watcher() {
  local seen=$OUT/.seen
  : > $seen
  for i in {1..480}; do
    local sbs=(/private/var/folders/*/*/T/com.apple.aned/TemporaryItems(N) /private/var/folders/*/*/0/com.apple.aned/TemporaryItems(N) /private/var/folders/*/*/C/com.apple.aned/TemporaryItems(N))
    for d in $sbs; do
      for f in $d/*(N-.); do
        key="$f"
        grep -Fqx -- "$key" $seen 2>/dev/null && continue
        n=$(basename $f)
        ts=$(date +%H%M%S)
        cp -f "$f" "$OUT/${ts}_$n" 2>/dev/null && { echo "COPIED $f -> ${ts}_$n"; echo "$key" >> $seen; }
      done
    done
    sleep 0.25
  done
}
watcher > $OUT/watcher.log 2>&1 &
W=$!
sleep 1
echo "== watcher up (pid $W); triggering ANE JIT load as current GUI user =="
CHRIS_UID=$(id -u <user> 2>/dev/null || id -u)
cd /Volumes/data/OpenFox/dev_m5max_re/silicon-ledger
P27_UNIT=ANE P27_ITERS=30 launchctl asuser $CHRIS_UID sudo -u <user> \
  .venv-conv/bin/python -u results/EXP-027-nax/harness/p27_anpos_run.py \
  > $OUT/jit_load.log 2>&1
echo "jit load rc=$? (tail below)"; tail -2 $OUT/jit_load.log
# second trigger: fresh-identity MIL-compile via public recompile of the mutated bundle
D=/tmp/f128_op1c.mlmodelc
rm -rf $D && cp -R /tmp/f128_op1.mlmodelc $D 2>/dev/null && \
  printf '\n// v8 trigger bump %s\n' "$(date +%s)" >> $D/model.mil && \
  PROBE_LOOPS=5 launchctl asuser $CHRIS_UID sudo -u <user> /tmp/mlc_load $D > $OUT/load_mut.log 2>&1
echo "mut load rc=$?"; tail -1 $OUT/load_mut.log
sleep 4
kill $W 2>/dev/null
echo "== service processes seen during window (late check) =="
pgrep -lx ANECompilerServi || echo "(none alive now)"
echo "== captured =="; ls -la $OUT
for f in $OUT/*_model.src $OUT/*src $OUT/*mil(N); do echo "--- $f ---"; head -c 400 "$f"; echo; done
echo DONE
