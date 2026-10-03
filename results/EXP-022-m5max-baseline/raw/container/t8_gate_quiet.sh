#!/bin/zsh
cd /Volumes/data/OpenFox/dev_m5max_re/silicon-ledger
LOG=/Volumes/data/OpenFox/dev_m5max_re/exp022-raw/t8-latency-quiet-$(date -u +%Y%m%dT%H%M%SZ).log
.venv/bin/python -u bench/gate_reranker_ane.py > $LOG 2>&1
echo "gate rc=$? -> $LOG"
