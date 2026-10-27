#!/bin/sh
# run_lanes44 — EXP-044 C3/C4 timed matrix runner. Interleaves arms round-robin per shape
# (common-mode against window drift, EXP-037 doctrine). One TSV line per cell on stdout.
# usage: sh run_lanes44.sh decode|full
set -e
cd "$(dirname "$0")"
BIN=./lane_arms44
MODE=${1:-decode}
if [ "$MODE" = "decode" ]; then
  for K in 2048 4096 8192; do
    for ARM in f8 f16 bf16; do $BIN decode $K 300 $ARM; done
  done
else
  for M in 2048 4096; do
    REPS=$([ "$M" = 2048 ] && echo 500 || echo 150)
    for ARM in f8 f16 bf16 f32 i8; do $BIN time $M $REPS $ARM; done
  done
fi
