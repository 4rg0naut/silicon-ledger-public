#!/bin/sh
# gen_all.sh — THE single entry point for every generated file. Never hand-edit these files.
#
#   sh tools/gen_all.sh --write    regenerate in dependency order
#   sh tools/gen_all.sh --check    write nothing; exit 1 and print a diff if any file is stale
#
# Order: records -> registry view (TOOLS.md) -> SUMMARY.md -> COUNTS.json -> front-door counts.
# It never runs knowledge/ane/tools/openclaims_append.py: the spine is append-only and is never
# regenerated; that step stays in tools/kb_pipeline.sh.
set -eu
export LC_ALL=C
cd "$(git rev-parse --show-toplevel)"

mode=${1:---check}
case "$mode" in --write|--check) ;; *) echo "usage: sh tools/gen_all.sh --write|--check" >&2; exit 2;; esac

GEN="knowledge/ane/records tools/TOOLS.md results/SUMMARY.md results/COUNTS.json README.md tools/publish/public-content"

generate() {
    # kb_records.py exits 1 for "parse problems" (5 chapters without a jsonl block) while still writing
    # every record; kb_pipeline.sh only survives that because it pipes through tail. Hard failures are
    # gated by `kb_records.py validate` in kb_pipeline.sh, so here we only require the output files.
    python3 knowledge/ane/tools/kb_records.py extract >/dev/null || true
    [ -s knowledge/ane/records/all.jsonl ] || { echo "gen_all: records extraction produced no all.jsonl" >&2; exit 1; }
    python3 tools/registry.py --view >/dev/null
    python3 bench/results_table.py --summary >/dev/null
    python3 tools/gen_counts.py --write >/dev/null
    python3 tools/publish/render_counts.py --write >/dev/null
}

if [ "$mode" = "--write" ]; then
    generate
    echo "gen_all: regenerated ($GEN)"
    exit 0
fi

snap=$(mktemp -d)
trap 'rm -rf "$snap"' EXIT
for f in $GEN; do
    mkdir -p "$snap/$(dirname "$f")"
    cp -R "$f" "$snap/$f"
done

generate

stale=0
for f in $GEN; do
    if ! diff -r -q "$snap/$f" "$f" >/dev/null 2>&1; then
        stale=1
        echo "STALE: $f" >&2
        diff -r -u "$snap/$f" "$f" | head -40 >&2 || true
    fi
done

for f in $GEN; do
    rm -rf "$f"
    mkdir -p "$(dirname "$f")"
    cp -R "$snap/$f" "$f"
done

if [ "$stale" -ne 0 ]; then
    echo "gen_all --check: FAIL — generated files differ from their sources (run: sh tools/gen_all.sh --write)" >&2
    exit 1
fi
echo "gen_all --check: OK"
