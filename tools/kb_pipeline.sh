#!/bin/sh
# kb_pipeline.sh — THE standard gate set for this repo. Run this; don't remember the steps.
#
# Owner, 2026-10-10: after ~30 experiments the tooling had spread over five locations and nothing
# recorded which instrument was canonical, so work got duplicated. This is the single entry point:
# it runs every gate in order and stops at the first failure, so an agent cannot silently skip one.
#
# usage: sh tools/kb_pipeline.sh
set -eu
export LC_ALL=C                      # fr_FR box: Apple CLIs emit comma decimals (GOTCHAS-078)
cd "$(git rev-parse --show-toplevel)"

echo "== 1/5 instrument registry =="
python3 tools/registry.py --check

echo "== 2/5 records -> jsonl =="
python3 knowledge/ane/tools/kb_records.py | tail -1

echo "== 3/5 records validate =="
python3 knowledge/ane/tools/kb_records.py validate | grep -iE "records:|hard failures"

echo "== 4/5 spine append (emits new claims; never regenerates) =="
PY=${PYTHON:-.venv/bin/python}
"$PY" knowledge/ane/tools/openclaims_append.py | tail -3

echo "== 5/5 spine check =="
"$PY" knowledge/ane/tools/to_openclaims.py --check | tail -1

echo
echo "pipeline OK — claims/verifications must still be re-validated after any record edit"
