#!/bin/sh
# power_correlate.sh — WHICH process owns the GPU-power excursions?
#
# Motivation (owner, 2026-10-10): the Studio is driven over Screen Share from a MacBook Air, so
# screensharingd/sharingd hold wake assertions and VTEncoderXPCService (hardware video encode) is
# live. GPU idle power had already been seen swinging 25->104 mW in 30 s; this samples power and
# per-process CPU on the SAME 1 Hz grid so the spikes can be attributed instead of guessed.
#
# usage: sh power_correlate.sh [seconds] [label]     # default 45 s
# writes: results/power-corr-<stamp>-<label>.tsv  (sec, gpu_mW, then cpu% for each watch process)
set -u
export LC_ALL=C   # ps prints comma decimals under a fr locale -> breaks float parsing
secs=${1:-45}
label=${2:-screen-share}
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
out="$here/../results/power-corr-$stamp-$label.tsv"
procs="/tmp/pc_procs.$$.tsv"
pjson="/tmp/pc_power.$$.jsonl"

# 1. power on a 1 Hz grid (our own tool, unprivileged)
"$root/tools/enginemon/enginemon" --interval 1000 --duration "$secs" --json --out "$pjson" >/dev/null 2>&1 &
ep=$!

# 2. per-process CPU on the same grid. Groups: screen-share path vs Apple background ML vs our own.
WATCH="VTEncoderXPCService screensharingd sharingd WindowServer avconferenced mediaanalysisd photoanalysisd photolibraryd mds_stores corespotlightd aned oMLX omlx-server"
echo -e "sec\tproc\tcpu" > "$procs"
i=0
while [ $i -lt "$secs" ]; do
  sleep 1
  i=$((i+1))
  for p in $WATCH; do
    pids=$(pgrep -x "$p" 2>/dev/null | tr '\n' ',' | sed 's/,$//')
    [ -n "$pids" ] || continue
    c=$(ps -o pcpu= -p "$pids" 2>/dev/null | awk '{s+=$1} END{printf "%.1f", s+0}')
    printf "%s\t%s\t%s\n" "$i" "$p" "$c" >> "$procs"
  done
done
wait $ep 2>/dev/null

# 3. join and report
python3 - "$pjson" "$procs" "$out" "$label" <<'PY'
import json, sys, statistics, collections
pjson, procs, out, label = sys.argv[1:5]
rows=[json.loads(l) for l in open(pjson) if l.strip()]
gpu={}
idx=0
for r in rows:
    if r.get('t')!='s': continue
    idx+=1
    for c in r.get('ch',[]):
        if c.get('n')=='GPU Energy' and isinstance(c.get('d'),(int,float)):
            gpu[idx]=c['d']/(r.get('dt') or 1.0)/1e6   # mW
cpu=collections.defaultdict(dict)
for line in open(procs).read().splitlines()[1:]:
    s,p,c=line.split('\t'); cpu[p][int(s)]=float(c.replace(',','.'))
secs=sorted(gpu)
with open(out,'w') as f:
    hdr=["sec",f"gpu_mW[{label}]"]+sorted(cpu)
    f.write("\t".join(hdr)+"\n")
    for s in secs:
        f.write("\t".join([str(s),f"{gpu[s]:.1f}"]+[f"{cpu[p].get(s,0.0):.1f}" for p in sorted(cpu)])+"\n")
vals=[gpu[s] for s in secs]
q=statistics.quantiles(vals,n=4) if len(vals)>3 else [min(vals)]*3
print(f"GPU mW: n={len(vals)} min={min(vals):.1f} p25={q[0]:.1f} med={statistics.median(vals):.1f} p75={q[2]:.1f} max={max(vals):.1f}")
base=statistics.median(vals); spikes=[s for s in secs if gpu[s] > base*1.5]
print(f"threshold 1.5x median = {base*1.5:.1f} mW -> {len(spikes)} spike seconds")
if spikes:
    print("\nspike seconds: gpu_mW | top CPU contributors (of the watchlist)")
    for s in spikes:
        tops=sorted(((cpu[p].get(s,0.0),p) for p in cpu), reverse=True)[:3]
        print(f"  t={s:3d}  {gpu[s]:6.1f} | " + "  ".join(f"{p}={c:.1f}%" for c,p in tops if c>0))
print(f"\nwrote {out}")
PY
if [ -s "$out" ]; then rm -f "$pjson" "$procs"; else echo "keeping raw: $pjson $procs"; fi
