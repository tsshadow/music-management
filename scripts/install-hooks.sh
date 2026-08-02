#!/bin/bash
# scripts/install-hooks.sh
# Points this clone's hooks at the versioned ones in scripts/hooks/.
# Run once after cloning. Safe to re-run.
#
# Uses core.hooksPath rather than copying files, so a hook change lands with a
# git pull instead of needing everyone to re-run this script.

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

chmod +x scripts/hooks/*
git config core.hooksPath scripts/hooks

echo "Git hooks now run from scripts/hooks/ (git config core.hooksPath)."
echo "Installed hooks:"
ls -1 scripts/hooks/
