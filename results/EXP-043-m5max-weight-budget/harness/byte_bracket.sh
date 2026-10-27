#!/bin/sh
# byte_bracket.sh — EXP-043: h17c ANE weight-byte bracket at fixed count (shared single blob).
# Extends EXP-021 (which proved count==weight-FILES, M4/h16g: 16 files then refusal; 128 refs OK).
# Here the COUNT is held (32 convs, one blob file) and BYTES are varied -> the byte budget for h17c.
# Second ladder holds bytes-ish (C=1024) and varies count -> h17c file-less count budget.
# Accept/refuse + correctness are the verdict; timing rides along but is stamped by the window key.
set -u
export LC_ALL=C
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
BIN=${BIN:-/tmp/ane-dma-test}
stamp=$(date -u +%Y%m%dT%H%M%SZ)
raw="$here/../raw"
mkdir -p "$raw"
echo "window-at-start: $(sh "$root/results/EXP-029-nax-crosslane/harness/quiet_probe.sh" exp043 2>/dev/null | grep QUIET-KEY)" | tee "$raw/bracket-$stamp.log"

echo "== byte ladder (nconv=32, seq=64, one shared blob; bytesMB=nconv*C*C*2) ==" | tee -a "$raw/bracket-$stamp.log"
for C in 2048 3072 4096 4608 5120; do
    BENCH_JSON="$raw/byte-$C-$stamp.json" SHAPES="$C,$C,64,32" SAME_SHAPE=1 SHARED_BLOB=1 ITERS=5 "$BIN" 2>&1 | grep -E "shared blob|Cin|FAILED|error" | tee -a "$raw/bracket-$stamp.log"
done

echo "== count ladder (C=1024, seq=64, one shared blob) ==" | tee -a "$raw/bracket-$stamp.log"
for N in 64 128 256 384; do
    BENCH_JSON="$raw/count-$N-$stamp.json" SHAPES="1024,1024,64,$N" SAME_SHAPE=1 SHARED_BLOB=1 ITERS=5 "$BIN" 2>&1 | grep -E "shared blob|Cin|FAILED|error" | tee -a "$raw/bracket-$stamp.log"
done
echo DONE | tee -a "$raw/bracket-$stamp.log"
