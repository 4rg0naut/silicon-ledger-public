#!/bin/sh
# nax_gemm_energy.sh — ABSOLUTE GPU energy per GEMM (no MLX leg), via enginemon + the nax_gemm probe.
#
# Why: the MetalHLO comparison runner always runs an MLX leg, so energy from it is a ratio, not a
# joule number. This wraps OUR probe (MetalHLO-only) in enginemon, so the window contains exactly
# the executions we count.
#
# usage: sh nax_gemm_energy.sh <M> [reps] [dtype] [arm]
#   arm: nax | coop | steel   (same env switches as nax_gemm_matrix.sh)
set -u
export LC_ALL=C
repo=/Volumes/data/OpenFox/dev_m5max_re
EM="$repo/silicon-ledger/tools/enginemon/enginemon"
BIN="$repo/tools/vendor/MetalHLO/.build/debug/nax_gemm"
[ -x "$EM" ] && [ -x "$BIN" ] || { echo "missing enginemon or nax_gemm"; exit 1; }

M=${1:?usage: nax_gemm_energy.sh <M> [reps] [dtype] [arm]}
reps=${2:-10}
dt=${3:-f16}
arm=${4:-nax}
case $arm in
    nax)   envs="METALHLO_NAX_GEMM=1" ;;
    coop)  envs="" ;;
    steel) envs="METALHLO_COOP_GEMM=0 METALHLO_FORCE_STEEL=1" ;;
    *)     echo "arm must be nax|coop|steel"; exit 2 ;;
esac

json=/tmp/gemm_energy.$$.jsonl
outlog=/tmp/gemm_energy.$$.out
# enginemon stops when the wrapped command exits, so --duration is just a cap.
env $envs METALHLO_DEBUG_MATMUL_PATH=1 "$EM" --interval 200 --duration 120 --json --out "$json" \
    -- "$BIN" "$M" "$M" "$M" "$reps" "$dt" > "$outlog" 2>&1

python3 - "$json" "$outlog" "$M" "$reps" "$dt" "$arm" "$envs" <<'PY'
import json, sys, statistics
jp, lp, M, reps, dt, arm, envs = sys.argv[1:8]
M = int(M); reps = int(reps)
rows = [json.loads(l) for l in open(jp) if l.strip()]
tot_nj = 0.0; sec = 0.0
for r in rows:
    if r.get('t') != 's':
        continue
    sec += r.get('dt') or 0.0
    for c in r.get('ch', []):
        if c.get('n') == 'GPU Energy' and isinstance(c.get('d'), (int, float)):
            tot_nj += c['d']
execs = 1 + 3 + reps                  # 1 correctness + 3 warmup + reps timed
flops = 2.0 * M * M * M
mj = tot_nj / 1e6
log = open(lp).read()
kernel = '?'
for line in log.splitlines():
    if '→' in line or '->' in line:
        kernel = line.split('→')[-1].split('->')[-1].strip().split(' ')[0]
        break
gflops = (flops * execs) / (sec * 1e9) if sec else 0.0
print(f"nax_gemm_energy\tM={M}\tdtype={dt}\tarm={arm}\tkernel={kernel}\treps={reps}\texecs={execs}\t"
      f"gpu_mJ={mj:.2f}\twindow_s={sec:.2f}\tmJ_per_GEMM={mj/execs:.3f}\tmJ_per_GFLOP={mj/(flops*execs/1e9):.2f}\t"
      f"mean_mW={tot_nj/sec/1e6 if sec else 0:.1f}\teffective_TFLOPs={gflops/1000.0:.3f}")
PY
rm -f "$json" "$outlog"
