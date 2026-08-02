#!/bin/bash
# scripts/test/music-management-unit.sh  
# Runs the Python unit tests for music_manager, tagger, scanner, importer and downloader.
# Usage: ./scripts/test/music-management-unit.sh [pytest-args...]

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

# Load .env if it exists (same convention as build.sh / scripts/lint.sh)
if [ -f .env ]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        clean_line=$(echo "$line" | sed 's/[[:space:]]*#.*$//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [[ -n "$clean_line" && "$clean_line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
            export "$clean_line"
        fi
    done < .env
fi

export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/services:$PYTHONPATH"

# Everything under services/ and tools/ is collected. This used to be a hand-maintained
# allow-list, which silently left ~half the existing test files out of both the run and
# the coverage figure. Discovery is governed by pytest.ini (python_files/norecursedirs)
# and the root conftest.py; new test files are picked up without editing this script.
TEST_TARGETS=(
    "services/"
    "tools/"
    # Pipeline policy: asserts .gitlab-ci.yml and the release scripts still obey
    # the rules that keep an untested commit from reaching production. Listed
    # explicitly because tests/ holds integration suites that this job must not
    # run, so the whole directory cannot be handed to pytest.
    "tests/ci/"
)

# Ratchet: the suite sits above this, and a change that drops below it fails here
# rather than silently eroding the figure. Raise it when coverage climbs; never
# lower it to make a red build green.
COVERAGE_MIN="${COVERAGE_MIN:-85}"

echo "--- Running music-management Python unit tests (min coverage: ${COVERAGE_MIN}%) ---"
# Not under `set -e`: a failing run must still leave a usable coverage report for
# the GitLab widget, so the exit code is captured and re-raised at the very end.
set +e
python3 -m pytest -p no:warnings \
    --cov=services \
    --cov-report=term \
    --cov-report=xml:coverage-python.xml \
    --cov-fail-under="$COVERAGE_MIN" \
    --junitxml=report-python.xml \
    "${TEST_TARGETS[@]}" "$@"
PYTEST_STATUS=$?
set -e

# Fix paths in Cobertura XML for GitLab visualization
# It changes filename="path/to/file" to filename="services/path/to/file"
# and sets <source> to the project root.
if [ -f coverage-python.xml ]; then
    echo "--- Fixing paths in coverage-python.xml ---"
    sed -i 's|filename="|filename="services/|g' coverage-python.xml
    sed -i 's|<source>.*</source>|<source>./</source>|g' coverage-python.xml
fi

exit "$PYTEST_STATUS"
