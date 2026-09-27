#!/bin/bash

# set_user_password.sh - CLI tool to set/change a user's password

# .env values are read the way docker-compose reads them (a `#` inside a
# value is not a comment); see scripts/lib/dotenv.sh and bug report 038.
# shellcheck source=scripts/lib/dotenv.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/dotenv.sh"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR" || exit 1

# Load environment variables
if [ -f .env ]; then
    dotenv_load .env
fi

# Ensure PYTHONPATH includes the project root
export PYTHONPATH="$ROOT_DIR"

# Run the python tool
python3 tools/set_password.py "$@"
