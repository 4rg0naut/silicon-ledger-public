#!/bin/zsh
# EXP-026 K4 v7 sudo capture (user-run): OP-BEARING MIL mutation + trigger
# assertions BEFORE the sandbox sweep (F-45 rule). Root-owned output: /tmp/p2b_capture.
#   sudo zsh harness/p2b_sudo_capture_v7.sh        (~70s)
OUT=/tmp/p2b_capture
[[ -d $OUT ]] && mv $OUT $OUT.prev.$(date +%s)
mkdir -p $OUT
TROOT=/private/var/folders/zz/zyxvpxvq6csfxvn_n0000000000000/T/com.apple.aned/TemporaryItems
SRC=/tmp/fresh128.mlmodelc
D=/tmp/f128_op1.mlmodelc
rm -rf $D; cp -R $SRC $D
# op-bearing mutation: first baked fp16 scalar const 0x1.6ap-3 -> 0x1.6bp-3
# (kernel constant changes; shapes untouched -> plan-build stays valid)
python3 - <<'PY'
p = "/tmp/f128_op1.mlmodelc/model.mil"
s = open(p).read()
needle = "tensor<fp16, []>(0x1.6ap-3)"
assert needle in s, "no mutation anchor"
s = s.replace(needle, "tensor<fp16, []>(0x1.6bp-3)", 1)
open(p, "w").write(s)
print("mutated:", needle, "-> 0x1.6bp-3")
PY
grep -q "tensor<fp16, \[\]>(0x1.6bp-3)" $D/model.mil && echo "ASSERT mutation-in-file OK" || { echo "ASSERT FAILED - abort"; exit 1; }
/usr/bin/fs_usage -w -f filesys,exec ANECompilerServi aned > $OUT/fsusage.txt 2>&1 &
FU=$!
SVC_PID=""
LOADI=0
for rep in 1 2; do
  echo "[load rep $rep]"
  PROBE_LOOPS=20 /tmp/mlc_load $D > $OUT/load_rep$rep.log 2>&1
  for i in {1..80}; do
    SVC_PID=$(pgrep -x ANECompilerServi)
    [[ -n $SVC_PID ]] && break
    sleep 0.05
  done
  [[ -n $SVC_PID ]] && echo "ASSERT svc-fired pid=$SVC_PID OK" || echo "svc NOT observed (rep $rep)"
done
NEWID=$(ls -t ~/Library/Caches/mlc_load/com.apple.e5rt.e5bundlecache/26A434 2>/dev/null | head -1)
[[ -n $NEWID ]] && echo "new-or-recent IDENT: $NEWID"   # root's copy lives in /var/root; informational
sleep 2
for f in $TROOT/NSIRD_ANECompilerService_*(N)/*(N); do
  n=$(basename $f); cp -f "$f" "$OUT/$n" 2>/dev/null && echo "copied $f"
done
kill $FU 2>/dev/null
echo "== captured =="; ls -la $OUT; echo DONE
