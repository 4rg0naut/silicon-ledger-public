#!/bin/zsh
# T8 quiet-window latency re-run (EXP-023), ssample-sandwiched for ANE-bandwidth proof.
# Cron/backgroud-scheduled after the EXP-022 03:17 capture; waits until cron.log gains a
# NEW DONE line before touching the Core AI runtime.
RAW=/Volumes/data/OpenFox/dev_m5max_re/exp022-raw
SIL=/Volumes/data/OpenFox/dev_m5max_re/silicon-ledger
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=$RAW/t8-latency-quiet-$TS.log
SSLOG=$RAW/t8-ssample-quiet-$TS.log
before=$(grep -c '^DONE' $RAW/cron.log 2>/dev/null)
for i in {1..30}; do
  now=$(grep -c '^DONE' $RAW/cron.log 2>/dev/null)
  [ "$now" -gt "$before" ] && break
  sleep 120
done
cd $SIL && $RAW/bin/ssample --duration 240 -- /bin/zsh $RAW/t8_gate_quiet.sh > $SSLOG 2>&1
echo "t8 latency rc=$? log=$LOG ssample=$SSLOG" >> $RAW/cron.log
