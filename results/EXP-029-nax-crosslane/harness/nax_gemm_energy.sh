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
repo=/data/OpenFox/dev_m5max_re
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
# Gates, taken from the probe's OWN stdout (it already prints both):
#   maxabs= <float>     correctness of the run  -> row fails if nonzero/absent
#   gpu_med_ms= <float> real GPU time per exec  -> duty = work/window
maxabs = None
gpu_ms = None
for line in log.splitlines():
    if 'maxabs=' in line:
        try: maxabs = float(line.split('maxabs=')[1].split()[0])
        except Exception: pass
    if 'gpu_med_ms=' in line:
        try: gpu_ms = float(line.split('gpu_med_ms=')[1].split()[0])
        except Exception: pass
work_s = (gpu_ms or 0.0) * execs / 1000.0
duty = work_s / sec if sec else 0.0
# A window that is mostly idle measures idle power, not the kernel: refuse it.
ok_correct = maxabs is not None and maxabs <= 0.0
ok_duty = duty >= 0.30
verdict = "PASS" if (ok_correct and ok_duty) else "FAIL"
unmet = []
if not ok_correct: unmet.append("maxabs")
if not ok_duty: unmet.append(f"duty<0.30")
print(f"nax_gemm_energy\tM={M}\tdtype={dt}\tpath_requested={arm}\tmaxabs={maxabs}\tduty={duty:.2f}\t"
      f"reps={reps}\texecs={execs}\tgpu_mJ={mj:.2f}\twindow_s={sec:.2f}\tmJ_per_GEMM={mj/execs:.3f}\t"
      f"mJ_per_GFLOP={mj/(flops*execs/1e9):.2f}\tmean_mW={tot_nj/sec/1e6 if sec else 0:.1f}\t"
      f"gpu_med_ms={gpu_ms}\tprobe_TFLOPs={(flops*execs)/(work_s*1e12) if work_s else 0:.2f}\t"
      f"verdict={verdict}{'' if verdict=='PASS' else ' unmet='+','.join(unmet)}")
print(f"# NOTE: path_requested is the arm's env switch, NOT observed attribution — the probe does\n"
      f"# not report which pipeline executed (METALHLO_DEBUG_MATMUL_PATH emits no kernel line here).")
PY
rm -f "$json" "$outlog"
