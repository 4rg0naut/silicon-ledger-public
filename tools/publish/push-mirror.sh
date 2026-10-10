#!/bin/sh
# push-mirror.sh — push the public staging tree to the GitHub mirror.
# Usage:  sh tools/publish/push-mirror.sh ["commit message"] [remote-url] [branch]
# Preconditions: staging built by tools/publish/publish.sh (deterministic tree).
# AUTH — WORKING PATH (established 2026-10-10): use the GitHub CLI credential helper. It stores a
# token in ~/.config/gh/hosts.yml, NOT in the login keychain, so it works in GUI, SSH-only and
# headless sessions alike:
#   gh auth login -h github.com -p https     # device code, no key pasting
#   gh auth setup-git                        # sets credential.https://github.com.helper
# Then plain HTTPS remotes work (the submodule origin is
# https://github.com/4rg0naut/silicon-ledger.git). Verify with: gh auth status
#
# SSH alternative (NOT active): the Studio key ~/.ssh/id_ed25519 (SHA256:A2GT26359heV7LJ7/
# ZooTnFFSi7OzIifDeOyeHGwj1M) is still unregistered; `gh ssh-key add` requires the
# admin:public_key scope which this token lacks (`gh auth refresh -h github.com -s
# admin:public_key` would grant it). Also note ~/.ssh/config for github.com previously set
# `IdentitiesOnly yes`, which makes ssh offer ONLY that IdentityFile and IGNORE agent keys — it
# was relaxed to `no` on 2026-10-10 (backup: config.bak-2026-10-10-agentforward).
#
# Historic note on the keychain route: over plain ssh the login keychain is not reachable, so the
# osxkeychain helper cannot answer and pushes fail with "could not read Username for
# 'https://github.com'"; `security unlock-keychain ~/Library/Keychains/login.keychain-db` fixes it
# for one session only.
#
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
