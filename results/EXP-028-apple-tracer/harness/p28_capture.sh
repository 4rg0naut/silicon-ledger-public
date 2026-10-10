#!/bin/bash
# p28_capture.sh OUTFILE PREDICATE -- RUNCMD...
# Streams matching events to OUTFILE (jsonl) while running RUNCMD, then stops the
# stream. Bounded; safe under quiet-window policy.
set -u
OUT="$1"; shift
PRED="$1"; shift
[ "$1" = "--" ] && shift
mkdir -p "$(dirname "$OUT")"
( /usr/bin/log stream --style ndjson --level debug --timeout 60 --predicate "$PRED" > "$OUT" ) &
STREAM=$!
sleep 2
"$@"
sleep 1
kill "$STREAM" 2>/dev/null
wait "$STREAM" 2>/dev/null
wc -l "$OUT"
