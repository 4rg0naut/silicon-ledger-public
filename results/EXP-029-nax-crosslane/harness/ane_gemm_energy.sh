#!/bin/sh
# ane_gemm_energy.sh — GPU energy + ANE ACTIVITY for one CoreML GEMM run (unprivileged).
#
# Constraint we must not paper over: on this box the ANE *energy* rail is NOT readable unprivileged
# (Energy Model -> ANE0 reads frozen; enginemon README). The real rail needs sudo powermetrics
# (~261 mW lane-specific, measured 2026-10-06). So this wrapper reports:
#   * GPU Energy  -> valid, and it tells you when the GPU (not the ANE) did the work
#   * SOC-NI9 'ANEXL U' -> the calibrated ANE-exclusive ACTIVITY lens (0 when idle by construction)
# and prints an explicit note that ANE joules require the sudo window.
#
# usage: sh ane_gemm_energy.sh <model.mlpackage> <M> <N> <K> [reps] [label]
set -u
export LC_ALL=C
repo=/Volumes/data/OpenFox/dev_m5max_re
EM="$repo/silicon-ledger/tools/enginemon/enginemon"
PROBE="$repo/silicon-ledger/results/EXP-029-nax-crosslane/harness/ane_gemm_probe.py"
V=${PYTHON:-/Volumes/data/OpenFox/AI_dev/silicon-ledger-bench/tools/.venv/bin/python}
[ -x "$EM" ] || { echo "missing enginemon"; exit 1; }

model=${1:?usage: ane_gemm_energy.sh <model> <M> <N> <K> [reps] [label]}
M=${2:?}; N=${3:?}; K=${4:?}
reps=${5:-20}
label=${6:-model}

json=/tmp/ane_e.$$.jsonl; log=/tmp/ane_e.$$.out
"$EM" --interval 200 --duration 300 --json --out "$json" -- "$V" "$PROBE" "$model" "$M" "$N" "$K" "$reps" "$label" > "$log" 2>&1

grep -E "^ane_gemm" "$log" || true
python3 - "$json" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
gpu_nj = 0.0; anexl = 0; sec = 0.0
for r in rows:
    if r.get('t') != 's':
        continue
    sec += r.get('dt') or 0.0
    for c in r.get('ch', []):
        n = c.get('n') or ''
        d = c.get('d')
        if not isinstance(d, (int, float)):
            continue
        if n == 'GPU Energy':
            gpu_nj += d
        if 'ANEXL U' in n:          # calibrated ANE-exclusive activity lens
            anexl += d
print(f"ane_gemm_energy\twindow_s={sec:.2f}\tgpu_mJ={gpu_nj/1e6:.2f}\tANE_activity_ANEXL_U={int(anexl)}")
print("NOTE: ANE joules need the sudo powermetrics window; ANEXL U > 0 with low GPU mJ means the ANE did the work.")
PY
rm -f "$json" "$log"
