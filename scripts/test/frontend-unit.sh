#!/bin/bash
# scripts/test/frontend-unit.sh
# One frontend check, named by which. The CI jobs frontend:format,
# frontend:lint, frontend:typecheck and frontend:unit each call this with their
# own argument, so a red pipeline says which of the four broke from the job
# name alone -- and "run the formatter" is not reported the same way as "a test
# failed".
#
# Called with no argument it runs all four in the order that fails cheapest
# first, which is what the pre-commit hook and a local check want.
#
# Usage: ./scripts/test/frontend-unit.sh [format|lint|typecheck|unit|all]

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/services/frontend"
WHAT="${1:-all}"

cd "$FRONTEND_DIR"

if [ ! -d node_modules ]; then
    echo "--- Installing frontend dependencies ---"
    npm install
fi

run_format() {
    # `npm run format:check` existed in package.json from the start and no job
    # ever called it, which is how 96 of 125 files came to be unformatted --
    # the same way ktlint and Android Lint sat configured and unrun. Fix a
    # failure here with `npm run format`.
    echo "--- Checking frontend formatting (oxfmt) ---"
    npm run format:check
}

run_lint() {
    echo "--- Running frontend lint (oxlint + eslint) ---"
    npm run lint
}

run_typecheck() {
    echo "--- Running frontend typecheck (svelte-check) ---"
    npm run check
}

run_unit() {
    echo "--- Running frontend unit tests with coverage ---"
    npm run coverage

    # Fix paths in Cobertura XML for GitLab visualization
    COVERAGE_FILE="coverage/cobertura-coverage.xml"
    if [ -f "$COVERAGE_FILE" ]; then
        echo "--- Fixing paths in $COVERAGE_FILE ---"
        sed -i 's|filename="|filename="services/frontend/|g' "$COVERAGE_FILE"
        sed -i 's|<source>.*</source>|<source>./</source>|g' "$COVERAGE_FILE"
    fi
}

case "$WHAT" in
    format)    run_format ;;
    lint)      run_lint ;;
    typecheck) run_typecheck ;;
    unit)      run_unit ;;
    all)       run_format; run_lint; run_typecheck; run_unit ;;
    *)         echo "Unknown check: $WHAT (format|lint|typecheck|unit|all)" >&2; exit 2 ;;
esac
