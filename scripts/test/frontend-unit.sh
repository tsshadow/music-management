#!/bin/bash
# scripts/test/frontend-unit.sh
# Every static check the frontend has, in the order that fails cheapest first:
# formatting, lint, typecheck, then the Vitest suite with coverage.
# Usage: ./scripts/test/frontend-unit.sh

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/services/frontend"

cd "$FRONTEND_DIR"

if [ ! -d node_modules ]; then
    echo "--- Installing frontend dependencies ---"
    npm install
fi

# Formatting first: it is the cheapest check and the one whose failure is
# fixed by a single command. `npm run format:check` existed in package.json
# from the start and no job ever called it, which is how 96 of 125 files came
# to be unformatted -- the same way ktlint and Android Lint sat configured and
# unrun. Fix a failure here with `npm run format`.
echo "--- Checking frontend formatting (oxfmt) ---"
npm run format:check

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
