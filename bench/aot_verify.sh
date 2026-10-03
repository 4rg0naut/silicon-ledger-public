#!/bin/bash
# AOT-compile a Core AI graph and VERIFY the bundle actually loads.
# A full disk can produce a correctly-SIZED but incompletely-written .aimodelc, which fails only
# at load_function with a diagnostic-free SIGSEGV. Size checks do not catch it; a load does.
set -u
SRC="$1"; OUT="$2"; ARCH="${3:-h17g}"
CB=$(ls -d /private/var/run/com.apple.security.cryptexd/mnt/com.apple.MobileAsset.MetalToolchain-*/Metal.xctoolchain/usr/bin/coreai-build 2>/dev/null | head -1)
[ -x "$CB" ] || { echo "  coreai-build not found"; exit 1; }
df -h "$(dirname "$OUT")" | tail -1 | awk '{print "  free before AOT: "$4}'
mkdir -p "$OUT"
"$CB" compile "$SRC" --output "$OUT" --preferred-compute neural-engine --architecture "$ARCH" >/tmp/aot_verify.err 2>&1
rc=$?
[ $rc -eq 0 ] || { echo "  AOT FAILED rc=$rc"; grep -i error /tmp/aot_verify.err | head -3; exit 1; }
B=$(ls -d "$OUT"/*.aimodelc 2>/dev/null | head -1)
[ -n "$B" ] || { echo "  no bundle produced"; exit 1; }
N=$(find "$B" -name '*ANE_region*' | wc -l | tr -d ' ')
echo "  bundle: $(basename "$B")  regions=$N"
[ "$N" -gt 0 ] || { echo "  FAIL: 0 ANE regions (silent GPU fallback)"; exit 1; }
echo "  sha256: $(shasum -a 256 "$B"/main.hash 2>/dev/null | cut -c1-16)…"
echo "  free after AOT:  $(df -h "$(dirname "$OUT")" | tail -1 | awk '{print $4}')"
echo "  OK — now LOAD it to prove the artifact is complete"
