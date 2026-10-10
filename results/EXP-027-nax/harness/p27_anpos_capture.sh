#!/bin/zsh
# EXP-027 AN-POS capture driver: idle / ANE-preferred / GPU-preferred / idle
# windows through enginemon (user-mode). Outputs raw/p27_anpos_*.jsonl.
set -u
cd /Volumes/data/OpenFox/dev_m5max_re/silicon-ledger
EM=/tmp/p27_enginemon
OUT=results/EXP-027-nax/raw
PY=.venv-conv/bin/python
RUN=results/EXP-027-nax/harness/p27_anpos_run.py

echo "== idle1 =="
$EM --interval 1000 --duration 12 --all --json --out $OUT/p27_anpos_idle1.jsonl > /dev/null 2>&1
echo "== ane (JIT load ~30s + steady loop) =="
P27_UNIT=ANE P27_ITERS=45 $EM --interval 1000 --duration 95 --all --json --out $OUT/p27_anpos_ane.jsonl -- $PY $RUN > /tmp/p27_anpos_ane.log 2>&1
tail -2 /tmp/p27_anpos_ane.log
echo "== gpu =="
P27_UNIT=GPU P27_ITERS=45 $EM --interval 1000 --duration 95 --all --json --out $OUT/p27_anpos_gpu.jsonl -- $PY $RUN > /tmp/p27_anpos_gpu.log 2>&1
tail -2 /tmp/p27_anpos_gpu.log
echo "== idle2 =="
$EM --interval 1000 --duration 12 --all --json --out $OUT/p27_anpos_idle2.jsonl > /dev/null 2>&1
wc -l $OUT/p27_anpos_*.jsonl
