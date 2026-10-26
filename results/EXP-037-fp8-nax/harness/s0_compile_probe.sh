#!/bin/sh
# s0_compile_probe.sh — S0 preflight for EXP-037: does the Metal 4.0 compiler accept
# matmul2d with metal_fp8_e4m3_format operands on THIS OS/toolchain, and what does the
# f8 lowering look like? Compile-only; the run happens in fp8_ladder.
#
# usage: sh s0_compile_probe.sh [outdir]
set -u
export LC_ALL=C
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-$here/../raw/s0-$(date -u +%Y%m%dT%H%M%SZ)}
mkdir -p "$out"

# Extract the embedded MSL from the host (between the R"MSL( and )MSL" markers).
awk '/R"MSL\(/{f=1;next} /^\)MSL"/{f=0} f' "$here/fp8_ladder.m" > "$out/fp8_kernels.metal"
[ -s "$out/fp8_kernels.metal" ] || { echo "extract failed"; exit 1; }

SDK=$(xcrun --show-sdk-path)
echo "== toolchain" | tee "$out/s0.log"
xcrun metal --version 2>&1 | tee -a "$out/s0.log"

echo "== compile -std=metal4.1 (fp8 element types are gated behind metal4.1: __HAVE_METAL_FP8_E4M3_FORMAT_TYPE__; metal4.0 rejects the type)" | tee -a "$out/s0.log"
if xcrun metal -std=metal4.1 -isysroot "$SDK" -iframework "$SDK/System/Library/Frameworks" -c "$out/fp8_kernels.metal" -o "$out/fp8_kernels.air" 2>&1 | tee -a "$out/s0.log"; then :; fi
[ -f "$out/fp8_kernels.air" ] && echo "AIR: OK ($(wc -c < "$out/fp8_kernels.air") bytes)" | tee -a "$out/s0.log" \
    || echo "AIR: MISSING — compile failed" | tee -a "$out/s0.log"

echo "== llvm IR dump (heuristic lens only; runtime attribution is enginemon matched-A/B)" | tee -a "$out/s0.log"
xcrun metal -std=metal4.1 -isysroot "$SDK" -iframework "$SDK/System/Library/Frameworks" -S "$out/fp8_kernels.metal" -o "$out/fp8_kernels.ll" 2>>"$out/s0.log" \
    && { echo "functions:" | tee -a "$out/s0.log"
         grep -o 'define .* @[^ (]*' "$out/fp8_kernels.ll" | sed 's/define.*@/  @/' | sort -u | head -20 | tee -a "$out/s0.log"
         echo "f8-body lens: conversions vs matmul builtins" | tee -a "$out/s0.log"
         for pat in "e4m3" "fp8" "matmul" "unpack" "convert"; do
             n=$(grep -ci "$pat" "$out/fp8_kernels.ll" 2>/dev/null || true)
             printf '  %-8s %s hits\n' "$pat" "${n:-0}" | tee -a "$out/s0.log"
         done; }

echo "S0 artifacts in $out"
