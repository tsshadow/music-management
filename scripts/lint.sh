#!/bin/bash
# scripts/lint.sh
# Runs ruff and pylint over the Python sources.
#
# Both are configured in the repository (pyproject.toml, .pylintrc), never on
# the command line, so a laptop and the CI runner report the same findings.
#
# Usage: ./scripts/lint.sh [file_or_dir ...] [pylint-threshold]

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# shellcheck source=scripts/lib/python-tooling.sh
source "$ROOT_DIR/scripts/lib/python-tooling.sh"

# In CI always inside the tooling container (tooling_container_required),
# elsewhere only when ruff or pylint is missing from this host.
if tooling_container_required || { [ "${PYTHON_TOOLING_CONTAINER:-0}" != "1" ] \
   && { ! have_tool ruff || ! have_tool pylint; }; }; then
    rerun_in_container ./scripts/lint.sh "$@"
fi

# Load .env if it exists to get any environment variables
if [ -f .env ]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Strip trailing comments and whitespace
        clean_line=$(echo "$line" | sed 's/[[:space:]]*#.*$//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [[ -n "$clean_line" && ! "$clean_line" =~ ^# ]]; then
            export "$clean_line"
        fi
    done < .env
fi

TARGET=${1:-services/ tools/ tests/}
# Ratchet, same idea as COVERAGE_MIN in scripts/test/music-management-unit.sh:
# the codebase currently scores well above this. Raise it as the score climbs,
# never lower it to make a red build green.
FAIL_UNDER=${2:-9.5}

# Formatting is NOT checked here. It is its own job (backend:format, running
# ./scripts/format.sh --check), so that a red pipeline says which of the two
# went wrong from the job name alone -- and so that "run the formatter" and
# "fix a lint finding", which are very different amounts of work, are not
# reported as the same failure.
#
# The pre-commit hook still runs both.
echo "--- Running ruff (fast lint) on $TARGET ---"
# shellcheck disable=SC2086
ruff check $TARGET
echo "--- Ruff passed ---"

echo "--- Running pylint on $TARGET (fail-under: $FAIL_UNDER) ---"
# shellcheck disable=SC2086
if ! python3 -m pylint $TARGET --fail-under="$FAIL_UNDER"; then
    echo ""
    echo "ERROR: Pylint score too low!"
    exit 1
fi

echo "--- Pylint passed ---"
exit 0
