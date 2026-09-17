#!/bin/bash
# scripts/test/frontend-screenshots-pull.sh
# Copies the reference screenshots a frontend:e2e job produced back into the
# tree, so they can be reviewed and committed. The suite renders the production
# build on the CI runner (see tests/browser/screenshots.spec.js); this is how a
# refreshed set (MUMA_UPDATE_SNAPSHOTS=1) or a first reference for a new route
# gets from that job's artifacts into services/frontend/tests/browser/__screenshots__/.
# Usage: ./scripts/test/frontend-screenshots-pull.sh [ref]
#   ref defaults to the current branch; the last pipeline on it is used.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REF="${1:-$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD)}"
SNAPSHOTS="services/frontend/tests/browser/__screenshots__"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "--- Downloading frontend:e2e artifacts of the last pipeline on $REF ---"
glab job artifact "$REF" "frontend:e2e" --path "$TMP/"

if [ ! -d "$TMP/$SNAPSHOTS" ]; then
    echo "❌ ERROR: the artifacts hold no $SNAPSHOTS -- did the job get as far as the screenshot suite?"
    exit 1
fi

mkdir -p "$ROOT_DIR/$SNAPSHOTS"
cp -R "$TMP/$SNAPSHOTS/." "$ROOT_DIR/$SNAPSHOTS/"

echo "--- Reference screenshots now in the tree (review before committing) ---"
git -C "$ROOT_DIR" status --short -- "$SNAPSHOTS"
