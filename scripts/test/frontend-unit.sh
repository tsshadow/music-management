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

echo "--- Running frontend unit tests with coverage ---"
npm run coverage

# Fix paths in Cobertura XML for GitLab visualization
COVERAGE_FILE="coverage/cobertura-coverage.xml"
if [ -f "$COVERAGE_FILE" ]; then
    echo "--- Fixing paths in $COVERAGE_FILE ---"
    sed -i 's|filename="|filename="services/frontend/|g' "$COVERAGE_FILE"
    sed -i 's|<source>.*</source>|<source>./</source>|g' "$COVERAGE_FILE"
fi
