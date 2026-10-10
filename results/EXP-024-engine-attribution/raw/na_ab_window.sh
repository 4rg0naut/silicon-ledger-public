#!/bin/bash
# C6+C7 quiet-window run — NA matched A/B with rails. USER-run (NOT sudo bash):
# only powermetrics needs root; the Metal harness must stay in your GUI session.
# Prompts for sudo ONCE at start, then keeps the ticket alive.
# Prereq: oMLX stopped (quiet-window rule), machine idle. Takes ~6 min.
#
# bash results/EXP-024-engine-attribution/raw/na_ab_window.sh
#
# Produces (under results/EXP-024-engine-attribution/raw/na-ab-<stamp>/):
#   powermetrics.txt      sudo gpu_power 250ms stream covering all phases
#   enginemon_{idle,armA,armB}.jsonl  unprivileged unfiltered streams per phase
#   na_tiles_arm{A,B}.log   C6 harness output (checksums + GFLOPS per arm)
#   summary.txt           ΔmW / ΔmJ-per-million-tiles vs HAL ceilings (auto)
set -euo pipefail
if [ "$(id -u)" = 0 ]; then
  # Fail before any sampling instead of after ~6 min of GAP lines: the Metal
  # payload must run in the GUI login session (root IOSurface path fails).
  echo "ERROR: USER-run, not sudo bash. Run as your GUI user: bash ${0#./} — the script sudo's powermetrics itself." >&2
  exit 1
fi
cd "$(dirname "$0")/../../.."        # -> repo root
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT=results/EXP-024-engine-attribution/raw/na-ab-$STAMP
mkdir -p "$OUT"
echo "out=$OUT"
sudo -v
( while sleep 30; do sudo -n true; done ) & KEEP=$!
trap 'kill $KEEP 2>/dev/null || true' EXIT

pm_start() { sudo powermetrics --samplers gpu_power -i 250 -n "$2" > "$1" 2>&1 & echo $!; }
phase() {
  local tag=$1 secs=$2; shift 2
  echo "-- phase $tag (${secs}s window)"
  pm_start "$OUT/powermetrics_$tag.txt" $((secs*4)) > "$OUT/.pmpid"
  tools/enginemon/enginemon --unfiltered --interval 500 --duration "$secs" --json \
      > "$OUT/enginemon_$tag.jsonl" 2>/dev/null &
  local empid=$!
  if [ "$#" -gt 0 ]; then
    if [ "$(id -u)" = 0 ] && [ -n "${SUDO_USER:-}" ]; then
      # Metal IOSurface allocs fail in a root session; run payload as the invoking user
      sudo -u "#${SUDO_UID:-$(id -u "$SUDO_USER")}" HOME="/Users/$SUDO_USER" \
           USER="$SUDO_USER" LOGNAME="$SUDO_USER" "$@" || echo "PAYLOAD $tag rc=$?"
    else
      "$@" || echo "PAYLOAD $tag rc=$?"
    fi
  fi
  wait $empid 2>/dev/null || true
  wait $(cat "$OUT/.pmpid") 2>/dev/null || true
}

arm_phase() {
  local tag=$1 win=$2; shift 2
  echo "-- phase $tag (${win}s window, relauncher)"
  tools/enginemon/enginemon --unfiltered --interval 500 --duration "$win" --json \
      > "$OUT/enginemon_$tag.jsonl" 2>/dev/null &
  local empid=$!
  pm_start "$OUT/powermetrics_$tag.txt" $((win*4)) > "$OUT/.pmpid"
  local start; start=$(date +%s)
  # IOSurface leak: ~1 surface/predict, client cap 16384 -> keep <=15000 predicts/process, relaunch per batch
  while [ $(( $(date +%s) - start )) -lt $((win-8)) ]; do
    echo "=== launch $(date -u +%FT%TZ)" | tee -a "$OUT/na_tiles_$tag.log"
    .venv-conv/bin/python -u "$@" 2>&1 | tee -a "$OUT/na_tiles_$tag.log" || echo "PAYLOAD $tag rc=$?"
  done
  wait $empid 2>/dev/null || true
  wait $(cat "$OUT/.pmpid") 2>/dev/null || true
}
echo "== idle floor =="
phase idle 30
echo "== arm A tensorops 64x32 =="
arm_phase armA 90 bench/na_tiles.py --iters 5000 --rounds 3 --tag tensorops
echo "== arm B simdgroup =="
arm_phase armB 90 bench/na_tiles.py --iters 5000 --rounds 3 --tag simdgroup
echo "== idle re-check =="
phase idle2 30

python3 - "$OUT" <<'PY'
import re,sys
out=sys.argv[1]
def parse(p):
    mw=[]; clk=[]
    try:
        for t in open(p):
            m=re.search(r'GPU Power:\s*([\d.]+)\s*mW',t)
            if m: mw.append(float(m.group(1)))
            m=re.search(r'GPU HW active frequency:\s*([\d.]+)\s*MHz',t)
            if m and float(m.group(1))>0: clk.append(float(m.group(1)))
    except FileNotFoundError:
        pass
    return mw,clk
res={}
for t in ['idle','armA','armB','idle2']:
    mw,clk=parse(f"{out}/powermetrics_{t}.txt")
    res[t]=(sum(mw)/len(mw) if mw else None, sorted(clk)[len(clk)//2] if clk else None, len(mw))
print("phase      mean_mW   med_clkMHz  samples")
for t,(m,c,n) in res.items():
    print(f"{t:9s} {m if m is None else round(m,1)}   {c}   {n}")
idles=[v[0] for k,v in res.items() if k.startswith('idle') and v[0]]
base=sum(idles)/len(idles) if idles else None
spread=(max(idles)-min(idles)) if idles else None
ITERS=5000; WIN=90
for arm in ('armA','armB'):
    m=res[arm][0]; clk=res[arm][1]
    us=[]
    lg=f"{out}/na_tiles_{arm}.log"
    try:
        for line in open(lg):
            mm=re.search(r'([\d.]+)\s*us/predict',line)
            if mm: us.append(float(mm.group(1)))
    except FileNotFoundError:
        pass
    if not (m and base and us):
        print(f"{arm}: mean={m} base={base} rounds_parsed={len(us)} — no figure (declare GAP)")
        continue
    tiles=len(us)*ITERS
    d=m-base
    dMJ=d*WIN                      # mW x s = mJ spent above idle over the window
    dMJ_Mt=dMJ*1e6/tiles
    med=sorted(us)[len(us)//2]
    gf=64*32*64*2/(med*1e-6)/1e9
    ceff=32*1024*(clk or 1800)/1e6
    print(f"{arm}: rounds={len(us)} tiles={tiles} med={med:.1f}us -> {gf:.2f} GFLOPS")
    print(f"     dmean={d:+.1f} mW (idle base {base:.1f}, drift-spread {spread if spread is None else round(spread,1)})")
    print(f"     dMJ_per_million_tiles={dMJ_Mt:.2f}   (window-energy / completed-tiles; duty incl.)")
    print(f"     ceiling: HAL-32 fp16 @{(clk or 1800):.0f}MHz = {ceff:.2f} TF -> measured/ceiling = {gf/1e3/ceff*100:.3f}%")
print("If |dmean| <= idle drift-spread, declare WITHIN NOISE; do not fabricate.")
PY
grep -hE 'checksum|GFLOPS|VERDICT' "$OUT"/na_tiles_arm*.log 2>/dev/null || echo "(no arm logs captured — check enginemon phase streams)"
echo "done: $OUT"
