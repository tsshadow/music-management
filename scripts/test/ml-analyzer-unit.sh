#!/bin/bash
# scripts/test/ml-analyzer-unit.sh
# Runs the unit tests of the deprecated ml-analyzer, which the default suite
# (scripts/test/music-management-unit.sh) skips since 2026-09-25.
#
# Only the manual CI job backend:ml-analyzer-unit calls this. The service is disabled,
# not deleted, and this is how the kept code can still be checked; see
# services/ml-analyzer/DEPRECATED.md for why, and for what reviving it takes.
# No coverage floor: the service is omitted from the coverage figure on purpose.
#
# Usage: ./scripts/test/ml-analyzer-unit.sh [pytest-args...]

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

# Same interpreter and requirements as the default suite; see the comment in
# scripts/test/music-management-unit.sh.
# shellcheck source=scripts/lib/python-tooling.sh
source "$ROOT_DIR/scripts/lib/python-tooling.sh"
if tooling_container_required; then
    TOOLING_REQUIREMENTS="requirements.txt"
    tooling_use_ci_image
    rerun_in_container ./scripts/test/ml-analyzer-unit.sh "$@"
fi

export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/services:$PYTHONPATH"

echo "--- Running the deprecated ml-analyzer's unit tests ---"
python3 -m pytest -p no:warnings services/tests/MlAnalyzer*Test.py "$@"
