#!/bin/bash
# scripts/test/frontend-unit.sh
# Runs the frontend static checks. NOTE: there is currently no unit test tool
# (e.g. Vitest) configured in services/frontend/package.json — see
# docs/testing-inventory.md, open question #2. Until that is added (Phase 5),
# this script runs the closest available checks: lint + typecheck.
# Usage: ./scripts/test/frontend-unit.sh

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/services/frontend"

cd "$FRONTEND_DIR"

if [ ! -d node_modules ]; then
    echo "--- Installing frontend dependencies ---"
    npm install
fi

echo "--- Running frontend lint ---"
npm run lint

echo "--- Running frontend typecheck (svelte-check) ---"
npm run check

echo "--- NOTE: no unit test runner configured yet (see docs/testing-inventory.md) ---"
