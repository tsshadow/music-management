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

# tests/unit/test_downloader_real_ytdlp.py needs the real yt-dlp: how it treats an
# error under ignoreerrors is the whole question there, and mock_base replaces it
# for everything under services/. When this interpreter has no yt-dlp of its own,
# the version requirements.txt pins is put in a cache directory of its own (never
# into the interpreter) and added to PYTHONPATH, which the child interpreters that
# test starts inherit. yt-dlp is pure Python with no required dependencies. Only
# the first run after a requirements bump talks to PyPI; if that fails, those
# tests skip with a reason and the run goes on.
if ! python3 -c "import yt_dlp" >/dev/null 2>&1; then
    YTDLP_SPEC="$(grep -E '^yt-dlp[<>=~ ]' requirements.txt | head -n 1 | sed 's/[[:space:]]*#.*$//')"
    YTDLP_SPEC="${YTDLP_SPEC:-yt-dlp}"
    YTDLP_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/muma-unit-yt-dlp/$(echo "$YTDLP_SPEC" | sha256sum | cut -c1-16)"
    if [ ! -d "$YTDLP_DIR/yt_dlp" ]; then
        echo "--- Installing $YTDLP_SPEC for tests/unit into $YTDLP_DIR ---"
        python3 -m pip install --quiet --disable-pip-version-check --no-deps --target "$YTDLP_DIR" "$YTDLP_SPEC" \
            || echo "--- Could not install $YTDLP_SPEC; the tests/unit tests that need it will skip ---"
    fi
    if [ -d "$YTDLP_DIR/yt_dlp" ]; then
        export PYTHONPATH="$PYTHONPATH:$YTDLP_DIR"
    fi
fi

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
    # Tests that need the real mutagen (services/conftest.py stubs it for the whole
    # session). Each runs its mutagen work in a child interpreter, so the stub that
    # collecting services/ installs does not reach it.
    "tests/unit/"
)

# Ratchet: the suite sits above this, and a change that drops below it fails here
# rather than silently eroding the figure. Raise it when coverage climbs; never
# lower it to make a red build green.
COVERAGE_MIN="${COVERAGE_MIN:-93}"

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
