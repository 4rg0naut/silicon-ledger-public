#!/bin/bash
# p28_e1_signpost — os-log/signpost capture around public Core AI runs (EXP-028 E1).
# Two captures per arm:
#   proc  = events emitted BY the harness process (its own CoreAI signposts)
#   sys   = events from ANY process whose subsystem mentions coreai/anie/odie
# Unprivileged. Usage: bash p28_e1_signpost.sh [iters]
# Requires ./p28_run_bin: swiftc -O p28_coreai_run/main.swift -o p28_run_bin
# Default MODEL is machine-local; set MODEL=/path/to/x.aimodel on other boxes.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HERE/p28_run_bin"
ITERS="${1:-20}"
MODEL="${MODEL:-/Volumes/data/OpenFox/AI_dev/silicon-ledger-bench/models/coreai/deep_fp16.aimodel}"
OUTDIR="${OUTDIR:-$HERE/../raw/p28_e1_signpost}"
mkdir -p "$OUTDIR"

run_arm () {
  local arm="$1" unit; unit="$( [ "$arm" = cpuOnly ] && echo cpu || echo "$arm" )"
  local pids=()
  /usr/bin/log stream --style ndjson --timeout 60 \
    --predicate 'process == "p28_run_bin"' \
    > "$OUTDIR/${arm}_proc.ndjson" 2>/dev/null & pids+=($!)
  /usr/bin/log stream --style ndjson --timeout 60 \
    --predicate 'subsystem CONTAINS[c] "coreai" OR subsystem CONTAINS[c] "anie" OR subsystem CONTAINS[c] "odie" OR senderImagePath CONTAINS[c] "CoreAI"' \
    > "$OUTDIR/${arm}_sys.ndjson" 2>/dev/null & pids+=($!)
  sleep 1.5
  "$BIN" "$MODEL" "$ITERS" "$unit" > "$OUTDIR/${arm}_run.txt" 2>&1
  echo "run rc=$? arm=$arm"
  sleep 1.5
  kill "${pids[@]}" 2>/dev/null
  wait 2>/dev/null
  echo "$arm proc=$(wc -l < "$OUTDIR/${arm}_proc.ndjson") sys=$(wc -l < "$OUTDIR/${arm}_sys.ndjson")"
}

for arm in default neuralEngine gpu cpuOnly; do run_arm "$arm"; done
echo CAPTURE_DONE
