#!/bin/bash
# scripts/lint.sh
# Runs ruff and pylint over the Python sources.
#
# Both are configured in the repository (pyproject.toml, .pylintrc), never on
# the command line, so a laptop and the CI runner report the same findings.
#
# Usage: ./scripts/lint.sh [file_or_dir ...] [pylint-threshold]

# .env values are read the way docker-compose reads them (a `#` inside a
# value is not a comment); see scripts/lib/dotenv.sh and bug report 038.
# shellcheck source=scripts/lib/dotenv.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/dotenv.sh"
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
    dotenv_load .env
fi

TARGET=${1:-services/ tools/ tests/}
# Ratchet, same idea as COVERAGE_MIN in scripts/test/music-management-unit.sh:
# the codebase currently scores well above this. Raise it as the score climbs,
# never lower it to make a red build green.
FAIL_UNDER=${2:-9.87}

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

# Docstrings (AGENTS.md rule 5: every function and class says what it is for).
# .pylintrc disables missing-function-docstring and missing-class-docstring for
# the tree as a whole -- thousands of findings, mostly in tests -- so the rule was
# enforced nowhere. It is enforced here on the modules pyproject.toml already
# holds to the strict type-check standard, with no tolerance: that list only grows
# (see scripts/typecheck.sh), and a module joins it clean. Only on a full run; a
# run on named paths is somebody linting what they just touched.
if [ $# -eq 0 ]; then
    mapfile -t STRICT_PATHS < <(python3 - <<'PY'
import tomllib
from pathlib import Path

config = tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))
for override in config['tool']['mypy']['overrides']:
    if not override.get('check_untyped_defs'):
        continue
    for module in override['module']:
        path = Path(*module.removesuffix('.*').split('.'))
        if module.endswith('.*') or path.is_dir():
            print(f'{path}/')
        else:
            print(f'{path}.py')
PY
    )
    echo "--- Checking docstrings on ${#STRICT_PATHS[@]} strictly-checked modules ---"
    if ! python3 -m pylint --disable=all --enable=missing-function-docstring,missing-class-docstring \
        --score=n "${STRICT_PATHS[@]}"; then
        echo ""
        echo "ERROR: a strictly-checked module has an undocumented public function or class."
        exit 1
    fi
    echo "--- Docstrings present ---"
fi
exit 0
