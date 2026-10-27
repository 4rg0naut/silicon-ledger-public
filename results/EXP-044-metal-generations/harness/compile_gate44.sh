#!/bin/sh
# compile_gate44 — EXP-044 C2a: build the three offline gate metallibs on a metal4.1-capable
# toolchain and print versions. Run ON the toolchain box (Studio). Artifacts land next to script.
set -e
cd "$(dirname "$0")"
echo "== compile_gate44 $(date -u +%FT%TZ) toolchain: $(xcrun -sdk macosx metal --version | head -1) =="
xcrun -sdk macosx metal -std=metal4.0 -c gate_kernels44.metal -o ctl40.air
xcrun -sdk macosx metallib ctl40.air -o gate_ctl40.metallib
xcrun -sdk macosx metal -std=metal4.1 -c gate_kernels44.metal -o all41.air
xcrun -sdk macosx metallib all41.air -o gate_all41.metallib
if xcrun -sdk macosx metal -std=metal4.0 -c gate_kernels44.metal -o fp8on40.air 2>fp8on40.err; then
  echo "NOTE: fp8 type compiled at metal4.0 on this toolchain (gate widened?)"
else
  echo "metal4.0 + fp8 type -> REJECTED (expected; first line follows)"
  head -1 fp8on40.err
fi
ls -la gate_ctl40.metallib gate_all41.metallib
nm -gU gate_all41.metallib 2>/dev/null | grep -E "g_f16|g_f8|c_write" || true
