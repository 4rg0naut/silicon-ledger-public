#!/bin/sh
# nax_gemm_matrix.sh — dtype-fair, MLX-free GEMM matrix on the local nax_gemm probe.
#
# Sources of truth: the probe source lives in THIS pack (harness/nax_gemm/main.swift) and is copied
# into the gitignored vendored MetalHLO tree (Sources/nax_gemm) for an incremental Swift build:
#   swift build --product nax_gemm        (from tools/vendor/MetalHLO)
#
# Arms are selected by env (MetalHLO reads them at compile time):
#   nax   METALHLO_NAX_GEMM=1
#   coop  (none)                                  MPP cooperative tf32
#   steel METALHLO_COOP_GEMM=0 METALHLO_FORCE_STEEL=1     (fp32 only - the Steel path is fp32)
# NOTE: for f16 inputs the Steel arm is INELIGIBLE by design, so the f16 "steel" row is really the
# fallback ladder - the recorded kernel name tells you what actually ran.
#
# usage: sh nax_gemm_matrix.sh [reps] [dtype ...] [size ...]
set -u
export LC_ALL=C
here=$(cd "$(dirname "$0")" && pwd)
BIN=/Volumes/data/OpenFox/dev_m5max_re/tools/vendor/MetalHLO/.build/debug/nax_gemm
[ -x "$BIN" ] || { echo "build it first: cd tools/vendor/MetalHLO && swift build --product nax_gemm"; exit 1; }

reps=${1:-10}; shift 2>/dev/null || true
dtypes=${1:-"f16 f32"}; [ $# -gt 0 ] && shift
sizes=${*:-"1024 2048 4096"}
out="$here/../results/nax_gemm_matrix-$(date -u +%Y%m%dT%H%M%SZ).tsv"
printf "dtype\tM\tN\tK\tarm\tkernel\tmed_ms\tmin_ms\tp90_ms\tmaxabs\n" > "$out"

for dt in $dtypes; do
    for M in $sizes; do
        for arm in nax coop steel; do
            case $arm in
                nax)   envs="METALHLO_NAX_GEMM=1" ;;
                coop)  envs="" ;;
                steel) envs="METALHLO_COOP_GEMM=0 METALHLO_FORCE_STEEL=1" ;;
            esac
            tmp=/tmp/gemm_matrix.$$.txt
            env $envs METALHLO_DEBUG_MATMUL_PATH=1 "$BIN" "$M" "$M" "$M" "$reps" "$dt" > "$tmp" 2>&1
            k=$(grep -m1 -oE '(→|->)[[:space:]]?[A-Za-z0-9]+' "$tmp" | sed -E 's/(→|->)[[:space:]]?//')
            med=$(grep -m1 -oE 'gpu_med_ms=[0-9.]+' "$tmp" | cut -d= -f2)
            mn=$(grep -m1 -oE 'min_ms=[0-9.]+' "$tmp" | cut -d= -f2)
            p90=$(grep -m1 -oE 'p90=[0-9.]+' "$tmp" | cut -d= -f2)
            mabs=$(grep -m1 -oE 'maxabs=[0-9.e+-]+' "$tmp" | cut -d= -f2)
            printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$dt" "$M" "$M" "$M" "$arm" "${k:-?}" "${med:-?}" "${mn:-?}" "${p90:-?}" "${mabs:-?}" >> "$out"
            rm -f "$tmp"
        done
    done
done
echo "wrote $out"
column -t -s "$(printf '\t')" "$out" 2>/dev/null || cat "$out"
