#!/bin/sh
# e39_ab_marker.sh — EXP-039 matched-A/B wrapper for enginemon capture.
# Interleaves fp16/w8 arms with 8 s idle gaps so lane-window bursts align 1:1 with phases.
set -u
# provenance: first run on /data/OpenFox/dev_m5max_re/silicon-ledger
L=$(cd "$(dirname "$0")/../../.." && pwd)
R=$L/tools/granite-runner/.build/out/Products/Release/granite-runner
W=$L/work/exports/granite-embedding-97m
SRC=$L/work/granite-embedding-97m/source
REF=$L/work/granite-embedding-97m/fixtures/golden_s128.json
for phase in fp16 w8 w8 fp16; do
    sleep 8
    if [ "$phase" = fp16 ]; then M=$W/macos/fp16-s128-ane/granite97m_fp16_s128.aimodel; else M=$W/w8fp16/s128/granite97m_w8_fp16_s128.aimodel; fi
    echo "PHASE $phase start $(date -u +%H:%M:%S)" >&2
    $R "$M" "$SRC" "$REF" --compute neuralEngine --iters 100 2>/dev/null | grep -E "warm median" >&2
    echo "PHASE $phase end   $(date -u +%H:%M:%S)" >&2
done
echo DONE >&2
