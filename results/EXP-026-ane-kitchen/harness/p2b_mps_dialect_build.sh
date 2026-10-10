#!/bin/bash
# p2b_mps_dialect_build.sh — build + run the private-dialect stub plugin.
# Uses Homebrew LLVM's MLIR (headers + libMLIR). Prints an SSA listing of a
# cached mpsgraph bytecode file.
set -uo pipefail
LLVM="${LLVM:-/opt/homebrew/opt/llvm@22}"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${OUT:-/tmp/ane_private_dialects.dylib}"

if [ ! -f "$LLVM/include/mlir/IR/Dialect.h" ]; then
  echo "ERROR: MLIR headers not found under $LLVM (brew install llvm@22)" >&2
  exit 2
fi

clang++ -std=c++17 -fPIC -shared \
  -I"$LLVM/include" \
  "$HERE/p2b_mps_dialect_plugin.cpp" \
  -L"$LLVM/lib" -lMLIR -lLLVM -Wl,-rpath,"$LLVM/lib" \
  -o "$OUT" || exit 1
echo "built: $OUT"

FILE="${1:-}"
[ -z "$FILE" ] && { echo "usage: $0 <mpsgraph-file>"; exit 2; }
"$LLVM/bin/mlir-opt" --load-dialect-plugin="$OUT" \
  --allow-unregistered-dialect "$FILE"
