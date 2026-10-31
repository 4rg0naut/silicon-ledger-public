#!/bin/sh
# install.sh — point this clone's hooks at tools/hooks (core.hooksPath). Idempotent.
#   sh tools/hooks/install.sh [--uninstall]
set -eu
cd "$(git rev-parse --show-toplevel)"
if [ "${1:-}" = "--uninstall" ]; then
    git config --unset core.hooksPath || true
    echo "hooks: core.hooksPath unset"
    exit 0
fi
chmod +x tools/hooks/pre-commit
git config core.hooksPath tools/hooks
echo "hooks: core.hooksPath = $(git config core.hooksPath)"
