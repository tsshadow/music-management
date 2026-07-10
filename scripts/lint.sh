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

TARGET=${1:-services/}
FAIL_UNDER=${2:-8.5}

echo "--- Running pylint on $TARGET (fail-under: $FAIL_UNDER) ---"
if ! python3 -m pylint "$TARGET" --fail-under="$FAIL_UNDER"; then
    echo ""
    echo "❌ ERROR: Pylint score too low!"
    exit 1
fi

echo "--- Pylint passed ---"
exit 0
