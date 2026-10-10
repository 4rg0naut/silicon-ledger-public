#!/bin/zsh
# EXP-027 NX-D: full-channel (unfiltered) enginemon windows, idle vs sustained
# coreai matmul2d load, to find every M5 IOReport channel that reacts to NAX work.
# Outputs raw/p27_nxd_{idle1,load,idle2}.jsonl + /tmp logs.
set -u
cd /Volumes/data/OpenFox/dev_m5max_re/silicon-ledger
EM=/tmp/p27_enginemon
OUT=results/EXP-027-nax/raw
PY=.venv-conv/bin/python
LOAD=results/EXP-027-nax/harness/p27_load_coreai.py

echo "== idle1 (12s, unfiltered+all) =="
$EM --interval 1000 --duration 12 --all --unfiltered --json --out $OUT/p27_nxd_idle1.jsonl > /dev/null 2>&1
echo "== load (wrapped coreai matmul2d, ~30s steady) =="
$EM --interval 1000 --duration 95 --all --unfiltered --json --out $OUT/p27_nxd_load.jsonl -- $PY -u $LOAD --seconds 30 > /tmp/p27_nxd_load.log 2>&1
echo "load rc=$?"; tail -3 /tmp/p27_nxd_load.log
echo "== idle2 =="
$EM --interval 1000 --duration 12 --all --unfiltered --json --out $OUT/p27_nxd_idle2.jsonl > /dev/null 2>&1
wc -l $OUT/p27_nxd_*.jsonl
