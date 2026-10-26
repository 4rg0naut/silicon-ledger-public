#!/bin/sh
# fp8_matrix.sh — EXP-037 S2/S4: timed GEMM matrix, arms f8 | mix8 | f16 on identical shapes.
# Rows carry TFLOPS per arm (throughput lens) and per-dispatch floor at small M (latency lens).
# K is always %128==0 (fp8 documented 128B alignment; K%128==0 makes every slice offset aligned).
# usage: sh fp8_matrix.sh [reps_big] [reps_small]
set -u
export LC_ALL=C
here=$(cd "$(dirname "$0")" && pwd)
BIN=${BIN:-/tmp/fp8_ladder}
[ -x "$BIN" ] || { echo "build first: clang -fobjc-arc -O2 -o /tmp/fp8_ladder fp8_ladder.m -framework Metal -framework Foundation"; exit 1; }
rb=${1:-15}; rs=${2:-60}
out="$here/../results/fp8_matrix-$(date -u +%Y%m%dT%H%SZ).tsv"
mkdir -p "$here/../results"
printf "arm\tM\treps\tgpu_med_ms\tmin_ms\ttflops\n" > "$out"
for arm in f8 mix8 f16; do
    for M in 128 256 512;  do "$BIN" time $M $rs $arm 2>/dev/null | grep '^fp8_ladder' | sed 's/fp8_ladder\tarm=//;s/\tM=/\t/;s/\treps=/\t/;s/\tgpu_med_ms=/\t/;s/\tmin_ms=/\t/;s/\ttflops=/\t/' >> "$out"; done
    for M in 1024 2048 4096; do "$BIN" time $M $rb $arm 2>/dev/null | grep '^fp8_ladder' | sed 's/fp8_ladder\tarm=//;s/\tM=/\t/;s/\treps=/\t/;s/\tgpu_med_ms=/\t/;s/\tmin_ms=/\t/;s/\ttflops=/\t/' >> "$out"; done
done
column -t -s $'\t' "$out" | tee "$out.col"
echo "wrote $out"
