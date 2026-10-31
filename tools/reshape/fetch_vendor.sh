#!/bin/sh
# fetch_vendor.sh — verify or rebuild the vendored RE toolchains from tools/vendor/PINS.md.
#
#   sh tools/reshape/fetch_vendor.sh               verify the live clones (../tools/vendor) against the pins; read-only
#   sh tools/reshape/fetch_vendor.sh --into DIR    clone each upstream into DIR, check out the pin, apply its patch
#
# Never deletes or modifies the live clones. Exit 1 on any mismatch.
set -eu
cd "$(git rev-parse --show-toplevel)"
PATCHES="$(pwd)/tools/vendor/patches"
LIVE="$(cd .. && pwd)/tools/vendor"

# name|upstream|commit|patch|restored-file (clone-relative=repo-relative)
PIN_COREML="coreml_to_ane_hwx|https://github.com/freedomtan/coreml_to_ane_hwx.git|0da81de0551ec8b0c01f4e346d9e13129257da2d|coreml_to_ane_hwx.patch|"
PIN_METALHLO="MetalHLO|https://github.com/pedronahum/MetalHLO|44b3a04be0095296f9be95ce060e93045b69c367|MetalHLO.patch|Sources/nax_gemm/main.swift=results/EXP-029-nax-crosslane/harness/nax_gemm/main.swift"

rebuild() {
    IFS='|' read -r name url commit patch extra <<EOF
$1
EOF
    git clone -q "$url" "$2/$name"
    git -C "$2/$name" checkout -q "$commit"
    git -C "$2/$name" apply "$PATCHES/$patch"
    if [ -n "$extra" ]; then
        to=${extra%%=*}; from=${extra#*=}
        mkdir -p "$2/$name/$(dirname "$to")"
        cp "$from" "$2/$name/$to"
    fi
    echo "rebuilt $name @ $(git -C "$2/$name" rev-parse --short HEAD) (+ patch)"
}

verify() {
    IFS='|' read -r name url commit patch extra <<EOF
$1
EOF
    d="$LIVE/$name"
    bad=0
    if [ ! -d "$d/.git" ]; then echo "MISSING $name" >&2; return 1; fi
    head=$(git -C "$d" rev-parse HEAD)
    if [ "$head" != "$commit" ]; then
        echo "MISMATCH $name: HEAD $head != pin $commit" >&2; bad=1
    fi
    if ! git -C "$d" diff | cmp -s - "$PATCHES/$patch"; then
        echo "MISMATCH $name: live local diff differs from tools/vendor/patches/$patch" >&2; bad=1
    fi
    if [ -n "$extra" ]; then
        to=${extra%%=*}; from=${extra#*=}
        if ! cmp -s "$d/$to" "$from"; then echo "MISMATCH $name: $to differs from $from" >&2; bad=1; fi
    fi
    [ "$bad" -eq 0 ] && echo "ok $name @ $(echo "$head" | cut -c1-7)"
    return "$bad"
}

if [ "${1:-}" = "--into" ]; then
    dest=${2:?usage: --into DIR}
    mkdir -p "$dest"
    rebuild "$PIN_COREML" "$dest"
    rebuild "$PIN_METALHLO" "$dest"
    exit 0
fi

[ -d "$LIVE" ] || { echo "no live vendor dir at $LIVE" >&2; exit 1; }
rc=0
verify "$PIN_COREML" || rc=1
verify "$PIN_METALHLO" || rc=1
exit "$rc"
