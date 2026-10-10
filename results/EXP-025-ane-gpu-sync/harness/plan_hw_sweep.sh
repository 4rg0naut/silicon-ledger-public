#!/bin/sh
# plan_hw_sweep.sh — sweep EXPLICIT HxW shapes for one conv config (k, C).
#
# Where plan_flip_sweep.sh fixes W=H, this takes exact shapes, so a threshold can be bisected
# finely at a fixed kernel and channel count (used to separate kernel size from raw MACs).
#
# usage: sh plan_hw_sweep.sh <k> <C> <H1xW1,H2xW2,...>
set -eu

k=$1
C=$2
shapes=$3
here=$(cd "$(dirname "$0")" && pwd)
V=${PYTHON:-/Volumes/data/OpenFox/AI_dev/silicon-ledger-bench/tools/.venv/bin/python}
out=${TMPDIR:-/tmp}/plan_hw
mkdir -p "$out"
cd "$here"

printf "k\tC\tHxW\tmacs\tflops\tweights\tout_elems\tpreferred\n"
for s in $(echo "$shapes" | tr ',' ' '); do
    H=${s%x*}
    W=${s#*x}
    "$V" make_conv.py "$out/$k-$C-$H-$W.mlpackage" "$C" "$H" "$W" "$k" >/dev/null 2>&1
    M=$("$V" -c "print(f'{$H*$W*$C*$C*$k*$k:.5e}')")
    F=$("$V" -c "print(f'{2*$H*$W*$C*$C*$k*$k:.5e}')")
    P=$(./plan_devicesupport "$out/$k-$C-$H-$W.mlpackage" 2>/dev/null | grep -m1 "preferred=" | sed 's/.*preferred=//')
    printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" "$k" "$C" "$s" "$M" "$F" "$((C*C*k*k))" "$((H*W*C))" "$P"
done
