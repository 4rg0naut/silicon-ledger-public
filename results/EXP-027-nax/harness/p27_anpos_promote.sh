#!/bin/zsh
# EXP-027 AN-POS promotion — matched 3-arm matrix (idle / ANE / GPU, CPU control),
# repeated, to promote PMP0 SOC-NI9 "ANEXL U" + SOC-NI8 "ANE UP" from
# "positive candidate" to a calibrated unprivileged ANE-exclusive metric.
# Reuses the validated harness (p27_anpos_run.py) and enginemon.
# Output: results/EXP-027-nax/raw/promote/<arm><n>.jsonl
set -u
cd /Volumes/data/OpenFox/dev_m5max_re/silicon-ledger
EM=/tmp/p27_enginemon
OUT=results/EXP-027-nax/raw/promote
PY=.venv-conv/bin/python
RUN=results/EXP-027-nax/harness/p27_anpos_run.py
ITERS=${ITERS:-60}
mkdir -p $OUT

lane () {   # arm unit n duration
  local unit=$1 n=$2 dur=$3
  local lu=$(printf '%s' "$unit" | tr 'A-Z' 'a-z')
  echo "== ${unit}${n} =="
  P27_UNIT=$unit P27_ITERS=$ITERS $EM --interval 500 --duration $dur --all --json \
    --out $OUT/${lu}${n}.jsonl -- $PY $RUN >/tmp/p27_promote_${unit}${n}.log 2>&1
  grep -E "lane=|DONE" /tmp/p27_promote_${unit}${n}.log | tail -2
}
idle () {   # n duration
  local n=$1 dur=$2
  echo "== idle${n} =="
  $EM --interval 500 --duration $dur --all --json --out $OUT/idle${n}.jsonl >/dev/null 2>&1
}

idle 1 12
lane ANE 1 24
lane GPU 1 24
lane CPU 1 24
lane ANE 2 24
lane GPU 2 24
idle 2 12
echo "WINDOWS:"; wc -l $OUT/*.jsonl
