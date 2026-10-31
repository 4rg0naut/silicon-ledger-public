#!/bin/sh
# lab_scratch.sh — resolve LAB_SCRATCH and FAIL LOUDLY when it is unset, missing or not writable.
#
# Two ways to use it:
#   1. In a script (preferred): capture the path, and let `set -e` / the explicit check stop the script:
#          scratch=$(sh "$(git rev-parse --show-toplevel)/tools/lab_scratch.sh" silicon-ledger) || exit 1
#   2. From a shell: sh tools/lab_scratch.sh [project]   -> prints the path, exit 0; otherwise exit 1, no output on stdout.
#
# It is deliberately an executable, not a sourced file: a sourced `return 1` lets the caller carry on, and a
# caller that carries on with an empty path is the silent fallback this exists to prevent.
#
# There is NO default directory. A missing mount must stop the work, never read as a result
# (same failure class as "0 ANE regions" read as a tie, see ../.omp/WATCHDOG.md).
#
# Convention: LAB_SCRATCH=/data/scratch  (project dirs below it: silicon-ledger/, ...)
set -u

die() {
    echo "lab_scratch: $1" >&2
    echo "lab_scratch: set LAB_SCRATCH to the mounted scratch root, e.g. export LAB_SCRATCH=/data/scratch (see SCRATCH.md)" >&2
    exit 1
}

[ -n "${LAB_SCRATCH:-}" ] || die "LAB_SCRATCH is not set"
[ -d "$LAB_SCRATCH" ] || die "LAB_SCRATCH=$LAB_SCRATCH does not exist (volume not mounted?)"
[ -w "$LAB_SCRATCH" ] || die "LAB_SCRATCH=$LAB_SCRATCH is not writable"

echo "$LAB_SCRATCH${1:+/$1}"
