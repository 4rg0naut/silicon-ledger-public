#!/bin/sh
# plan_flip_sweep.sh — locate the CPU->ANE placement flip in conv FLOPs for one conv config.
#
# One conv, square input, H=W; prints FLOPs and the planner's preferred device per size, so the
# bracket can be compared ACROSS (kernel, channels) to test whether the gate is really conv FLOPs
# (kernel-scaled, API-147) or shape-dependent.
#
# usage: sh plan_flip_sweep.sh <k> <C> <H1,H2,...>     (W=H)
set -eu

k=$1
C=$2
sizes=$3
here=$(cd "$(dirname "$0")" && pwd)
V=${PYTHON:-/Volumes/data/OpenFox/AI_dev/silicon-ledger-bench/tools/.venv/bin/python}
out=${TMPDIR:-/tmp}/plan_flip
mkdir -p "$out"
cd "$here"

printf "k\tC\tH\tconv_flops\tpreferred\n"
for H in $(echo "$sizes" | tr ',' ' '); do
    "$V" make_conv.py "$out/$k-$C-$H.mlpackage" "$C" "$H" "$H" "$k" >/dev/null 2>&1
    F=$("$V" -c "print(f'{2*$C*$C*$k*$k*$H*$H:.5e}')")
    P=$(./plan_devicesupport "$out/$k-$C-$H.mlpackage" 2>/dev/null | grep -m1 "preferred=" | sed 's/.*preferred=//')
    printf "%s\t%s\t%s\t%s\t%s\n" "$k" "$C" "$H" "$F" "$P"
done
