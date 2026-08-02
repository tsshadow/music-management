#!/bin/bash
# scripts/lint.sh
# Usage: ./scripts/lint.sh [file_or_dir]

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

TARGET=${1:-services/ tools/}
# Ratchet, same idea as COVERAGE_MIN in scripts/test/music-management-unit.sh:
# the codebase currently scores well above this. Raise it as the score climbs,
# never lower it to make a red build green.
FAIL_UNDER=${2:-9.5}

echo "--- Running ruff (fast lint) on $TARGET ---"
if command -v ruff >/dev/null 2>&1; then
    # shellcheck disable=SC2086
    ruff check $TARGET
    echo "--- Ruff passed ---"
else
    echo "ruff not installed, skipping (pip install ruff)"
fi

echo "--- Running pylint on $TARGET (fail-under: $FAIL_UNDER) ---"
# shellcheck disable=SC2086
if ! python3 -m pylint $TARGET --fail-under="$FAIL_UNDER"; then
    echo ""
    echo "ERROR: Pylint score too low!"
    exit 1
fi

echo "--- Pylint passed ---"
exit 0
