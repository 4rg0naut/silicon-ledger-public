#!/bin/sh
# fp8_energy.sh — EXP-037 S3/S4: matched-A/B GPU energy + engagement windows for the fp8 ladder arms.
#
# Arms at identical shape: f8 (the question), mix8 (half x fp8), f16 (known-good tensor baseline).
# Attribution stance (EXP-027 NXD-P1, Apple tech-talk 111432): IOReport gives engagement lenses
# (PS13/UT), not an NAX verdict; the discriminating measurement is the matched-A/B GPU Energy delta
# plus the throughput table in fp8_matrix.sh. Window = one `fp8_ladder time` run = 1 precheck +
# 3 warmup + reps timed GEMMs.
#
# usage: sh fp8_energy.sh <M> [reps] [arm]
set -u
export LC_ALL=C
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../../../.." && pwd)
EM="$repo/silicon-ledger/tools/enginemon/enginemon"
BIN=${BIN:-/tmp/fp8_ladder}
[ -x "$EM" ] && [ -x "$BIN" ] || { echo "missing enginemon or fp8_ladder"; exit 1; }
M=${1:?usage: fp8_energy.sh <M> [reps] [arm]}
reps=${2:-30}
arm=${3:-f8}

json=/tmp/fp8_energy.$$.jsonl
outlog=/tmp/fp8_energy.$$.out
"$EM" --interval 200 --duration 120 --json --out "$json" -- "$BIN" time "$M" "$reps" "$arm" > "$outlog" 2>&1

python3 - "$json" "$outlog" "$M" "$reps" "$arm" <<'PY'
import json, sys
jp, lp, M, reps, arm = sys.argv[1:6]
M = int(M); reps = int(reps)
rows = [json.loads(l) for l in open(jp) if l.strip()]
tot_nj = 0.0; sec = 0.0; ps13 = 0.0; ch_names = {}
for r in rows:
    if r.get('t') != 's':
        continue
    sec += r.get('dt') or 0.0
    for c in r.get('ch', []):
        n = c.get('n'); d = c.get('d')
        if n == 'GPU Energy' and isinstance(d, (int, float)):
            tot_nj += d
        if isinstance(n, str) and 'Perf_State_13' in n and isinstance(d, (int, float)):
            ps13 = max(ps13, d)
        if isinstance(n, str):
            ch_names[n] = (r.get('g'), d)
execs = 1 + 3 + reps
flops = 2.0 * M * M * M
mj = tot_nj / 1e6
line = open(lp).read().strip().splitlines()
print("arm=%s M=%d execs=%d" % (arm, M, execs))
print("  GPU Energy window: %.1f mJ over %.2f s -> %.3f mJ/GEMM, %.1f mJ/TFLOP" %
      (mj, sec, mj / execs, mj / (flops / 1e12 * execs)))
print("  PS13 engagement max: %d" % ps13)
print("  channels seen: %d" % len(ch_names))
for l in line:
    if l.startswith('fp8_ladder') or 'precheck' in l:
        print("  run: " + l)
PY
