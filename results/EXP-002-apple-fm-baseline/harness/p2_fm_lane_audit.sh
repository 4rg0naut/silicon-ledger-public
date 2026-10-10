#!/bin/zsh
# p2_fm_lane_audit.sh — FM lane audit under enginemon (EXP-002 follow-up).
# Windows: idle1 / fm respond burst / fm serve warm / idle2, all --all JSON.
# Question: which lanes does Apple's on-device model actually use, and at what duty?
set -u
cd /Volumes/data/OpenFox/dev_m5max_re/silicon-ledger
EM=/tmp/em_fm; cp tools/enginemon/enginemon $EM
OUT=results/EXP-002-apple-fm-baseline/raw/lane-audit
mkdir -p $OUT
N=${N:-25}

echo "== idle1 =="
$EM --interval 500 --duration 12 --all --json --out $OUT/idle1.jsonl >/dev/null 2>&1

echo "== fm respond burst (n=$N) =="
$EM --interval 500 --duration 40 --all --json --out $OUT/fm_respond.jsonl -- \
  /bin/zsh -c "for i in \$(seq 1 $N); do /usr/bin/fm respond 'Reply with exactly one word: pong' >/dev/null 2>&1; done" \
  >/tmp/fm_respond.log 2>&1
tail -2 /tmp/fm_respond.log

echo "== idle2 =="
$EM --interval 500 --duration 12 --all --json --out $OUT/idle2.jsonl >/dev/null 2>&1

echo "WINDOWS:"; wc -l $OUT/*.jsonl
