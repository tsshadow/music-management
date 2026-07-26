#!/bin/bash

# set_user_password.sh - CLI tool to set/change a user's password

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Load environment variables
if [ -f .env ]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        clean_line=$(echo "$line" | sed 's/[[:space:]]*#.*$//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [[ -n "$clean_line" && ! "$clean_line" =~ ^# ]]; then
            if [[ "$clean_line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
                export "$clean_line"
            fi
        fi
    done < .env
fi

# Ensure PYTHONPATH includes the project root
export PYTHONPATH="$ROOT_DIR"

# Run the python tool
python3 tools/set_password.py "$@"
