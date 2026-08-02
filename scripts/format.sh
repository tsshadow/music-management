#!/bin/bash
# scripts/format.sh
# Opt-in code formatter. Not run in CI: a repository-wide reformat would rewrite
# almost every file at once and make every open branch conflict. Run it on the
# directory you are working in, review the diff, and commit it separately.
#
# Usage: ./scripts/format.sh [path ...]        (default: nothing, prints help)
#        ./scripts/format.sh --check [path]    (report only, no writes)

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v ruff >/dev/null 2>&1; then
    echo "ruff is not installed (pip install ruff)" >&2
    exit 1
fi

MODE=format
if [ "$1" = "--check" ]; then
    MODE=check
    shift
fi

if [ $# -eq 0 ]; then
    cat <<'USAGE'
Usage: ./scripts/format.sh [--check] <path> [path ...]

Deliberately requires an explicit path. Formatting the whole tree in one go is
a decision to take on purpose, not a default:

    ./scripts/format.sh services/importer          # one module
    ./scripts/format.sh --check services/importer  # see what would change
USAGE
    exit 1
fi

if [ "$MODE" = check ]; then
    ruff format --check --diff "$@"
else
    ruff format "$@"
    echo "--- Re-running the linter over the formatted files ---"
    ruff check --fix "$@"
fi
