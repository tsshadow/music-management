#!/bin/bash
# scripts/format.sh
# Formats the Python tree with `ruff format`, and is the thing quality:lint
# checks: since the one-off whole-tree reformat, formatting is enforced.
#
# It used to require an explicit path and warn that a repository-wide reformat
# "would rewrite almost every file at once and make every open branch
# conflict". Both were true, and it is done: 368 of 411 files, on a day with
# zero open merge requests. Defaulting to the whole tree is now the honest
# behaviour -- a formatter that only ever ran on the directory you remembered
# to point it at is how the tree drifted in the first place.
#
# Usage: ./scripts/format.sh                    # format services/ tools/ tests/
#        ./scripts/format.sh --check            # report only, no writes (CI)
#        ./scripts/format.sh services/importer  # one module, still works

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# shellcheck source=scripts/lib/python-tooling.sh
source "$ROOT_DIR/scripts/lib/python-tooling.sh"

# Same container fallback as scripts/lint.sh, so this works on a host without
# ruff -- which is every CI runner.
if [ "${PYTHON_TOOLING_CONTAINER:-0}" != "1" ] && ! have_tool ruff; then
    rerun_in_container ./scripts/format.sh "$@"
fi

MODE=format
if [ "$1" = "--check" ]; then
    MODE=check
    shift
fi

if [ $# -eq 0 ]; then
    set -- services/ tools/ tests/
fi

if [ "$MODE" = check ]; then
    ruff format --check "$@"
else
    ruff format "$@"
    echo "--- Re-running the linter over the formatted files ---"
    ruff check --fix "$@"
fi
