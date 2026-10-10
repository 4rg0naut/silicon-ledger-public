#!/bin/sh
# nax_lane_matrix.sh — GPU-resident lane matrix via MetalHLO's own comparison runner.
#
# Arms (all inside the GPU; NAX is a datapath per GPU core, see API-164):
#   nax   = MPP gemm_loop (MLX-grade cooperative tensor)      METALHLO_NAX_GEMM=1
#   coop  = MPP cooperative-tensor tf32 (the default)         (no switch)
#   steel = hand-rolled simdgroup_matrix shader/SIMT path     METALHLO_COOP_GEMM=0 METALHLO_FORCE_STEEL=1
# Correctness comes from the runner itself: it compares against MLX and prints ✅/❌.
# Every row also records WHICH kernel MetalHLO actually selected (METALHLO_DEBUG_MATMUL_PATH).
#
# usage: sh nax_lane_matrix.sh [reps] [shape ...]
#   default shapes: MAT-DOT-003 (1024^2) MAT-DOT-004 (2048^2) MAT-DOT-005 (4096^2) MAT-DOT-008 (decode)
set -u
export LC_ALL=C
here=$(cd "$(dirname "$0")" && pwd)
MH=/Volumes/data/OpenFox/dev_m5max_re/tools/vendor/MetalHLO
BIN="$MH/.build/debug/mlx-comparison"
[ -x "$BIN" ] || { echo "missing $BIN (build MetalHLO with Xcode, see EXP-027)"; exit 1; }

reps=${1:-2}
shift 2>/dev/null || true
shapes=${*:-"MAT-DOT-003 MAT-DOT-004 MAT-DOT-005 MAT-DOT-008"}
out="$here/../results/nax_lane_matrix-$(date -u +%Y%m%dT%H%M%SZ).tsv"
printf "shape\tarm\tkernel\tmhlo_ms\tmlx_ms\tok\n" > "$out"

for shape in $shapes; do
    for arm in nax coop steel; do
        case $arm in
            nax)   envs="METALHLO_NAX_GEMM=1" ;;
            coop)  envs="" ;;
            steel) envs="METALHLO_COOP_GEMM=0 METALHLO_FORCE_STEEL=1" ;;
        esac
        i=1
        while [ "$i" -le "$reps" ]; do
            tmp=/tmp/lane_matrix.$$.txt
            env $envs METALHLO_DEBUG_MATMUL_PATH=1 "$BIN" --quick --filter "$shape" > "$tmp" 2>&1
            # MetalHLO prints a Unicode arrow: '... → CoopTF32 (tg128=...)'
            k=$(grep -m1 -oE '(→|->)[[:space:]]?[A-Za-z0-9]+' "$tmp" | sed -E 's/(→|->)[[:space:]]?//')
            mh=$(grep -m1 -oE 'MetalHLO: [0-9.]+ms' "$tmp" | grep -oE '[0-9.]+')
            mx=$(grep -m1 -oE 'MLX: [0-9.]+ms' "$tmp" | grep -oE '[0-9.]+')
            ok=$(grep -c '✅' "$tmp")
            printf "%s\t%s\t%s\t%s\t%s\t%s\n" "$shape" "$arm" "${k:-?}" "${mh:-?}" "${mx:-?}" "$ok" >> "$out"
            rm -f "$tmp"
            i=$((i + 1))
        done
    done
done
echo "wrote $out"
column -t -s "$(printf '\t')" "$out" 2>/dev/null || cat "$out"
