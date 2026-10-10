#!/bin/zsh
cd /Volumes/data/OpenFox/dev_m5max_re/silicon-ledger/tools/enginemon
( PROBE_LOOPS=600 /tmp/mlc_load /tmp/fresh128.mlmodelc >/tmp/p2_par_probe.log 2>&1 ) &
PROBE=$!
sleep 0.6
ENGINEemon_ANE=1 ENGINEMON_DURATION=8 ./enginemon 2>&1 > /tmp/p2_enginemon_full.txt || ./enginemon > /tmp/p2_enginemon_full.txt 2>&1
wait $PROBE 2>/dev/null
grep -iE "ane|dcs|neural" /tmp/p2_enginemon_full.txt || echo "NO ANE CHANNELS FIRED"
grep -c "" /tmp/p2_enginemon_full.txt
