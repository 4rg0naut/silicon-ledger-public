#!/bin/sh
# push-mirror.sh — push the public staging tree to the GitHub mirror.
# Usage:  sh tools/publish/push-mirror.sh ["commit message"] [remote-url] [branch]
# Preconditions: staging built by tools/publish/publish.sh (deterministic tree).
# Identity is set per-command (MIRROR_NAME / MIRROR_EMAIL), NOT in the global git
# config — so this works on a machine whose global identity is unset (that was the
# manual step that failed once). A fresh clone in a temp dir keeps this stateless.
set -eu

repo=$(git rev-parse --show-toplevel)
stage="$repo/../silicon-ledger-public-staging"
msg=${1:-"mirror: sync public staging"}
remote=${2:-https://github.com/4rg0naut/silicon-ledger-public}
branch=${3:-main}
name=${MIRROR_NAME:-4rg0naut}
email=${MIRROR_EMAIL:-4rg0naut@users.noreply.github.com}

[ -d "$stage" ] || { echo "refusing: $stage missing — run tools/publish/publish.sh first" >&2; exit 1; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT INT TERM

git clone -q "$remote" "$tmp/m"
cd "$tmp/m"
find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -R "$stage/." .

git add -A
if git diff --cached --quiet; then
    echo "mirror unchanged; nothing to push"
    exit 0
fi
n=$(git diff --cached --numstat | wc -l | tr -d ' ')
src=$(git -C "$repo" rev-parse HEAD)   # CROSS-REPO-CONTRACT: each mirror commit names its source
git -c user.name="$name" -c user.email="$email" commit -q -m "$msg" -m "source-commit: $src"
git push -q origin "$branch"
echo "mirror pushed: $n files changed -> $remote ($branch)"
