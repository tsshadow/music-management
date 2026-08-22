#!/bin/bash
# scripts/test/e2e-gherkin.sh
# The scan-to-listen chain again, written as Gherkin instead of as a pytest
# function. Same stack, same fixture, same three steps -- see
# tests/bdd/features/scan_to_listen.feature.
#
# This is a pilot, which is why it is a separate manual job (e2e:gherkin) rather
# than a replacement for e2e:scan-to-listen. The question it exists to answer is
# whether a .feature file is a better description of this chain than the
# docstring on the test is. If it is, the plain test goes and this takes over the
# gating job; if it is not, deleting this script and tests/bdd/ costs nothing.
#
# Usage: ./scripts/test/e2e-gherkin.sh
#
# pytest-bdd is the runner rather than behave because it is a pytest plugin: it
# inherits pytest.ini, the `e2e` marker, the fixtures and the JUnit XML that
# GitLab reads for the merge request widget. behave brings its own runner, its
# own configuration and its own report format, all of which would have to be
# wired up a second time.
#
# The runners have pytest and requests in their system Python but not
# pytest-bdd, and this repository cannot install into that Python. So when the
# plugin is missing the suite runs inside the tooling image instead -- the same
# fallback scripts/lint.sh uses, with --network host added because the stack
# publishes its ports on the host and the tests reach them over 127.0.0.1.

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BDD_IMAGE="${PYTHON_TOOLING_IMAGE:-python:3.11-slim}"

# shellcheck source=scripts/lib/e2e-stack.sh
source "$ROOT_DIR/scripts/lib/e2e-stack.sh"

# A prefix of its own so a local run of this does not tear down a core-e2e.sh
# stack that is up at the same time.
e2e_stack_up muma-gherkin

echo "--- Running the Gherkin scan-to-listen feature ---"
cd "$ROOT_DIR"

if python3 -c 'import pytest_bdd' >/dev/null 2>&1; then
    python3 -m pytest -p no:warnings tests/bdd/ -v
else
    if ! command -v docker >/dev/null 2>&1; then
        echo "pytest-bdd is missing and Docker is not available." >&2
        echo "Install it with: pip install -r tests/bdd/requirements.txt" >&2
        exit 1
    fi
    echo "--- pytest-bdd not on PATH; running the feature inside $BDD_IMAGE ---"
    # --user keeps .pytest_cache and __pycache__ owned by the runner rather than
    # by root; root-owned build output is what the pre_get_sources_script hook in
    # .gitlab-ci.yml exists to clean up after.
    docker run --rm \
        --network host \
        --user "$(id -u):$(id -g)" \
        -v "$ROOT_DIR:/repo" \
        -w /repo \
        -e HOME=/tmp \
        -e PYTHONUSERBASE=/tmp/tooling \
        -e PIP_CACHE_DIR=/tmp/pip-cache \
        -e PATH=/tmp/tooling/bin:/usr/local/bin:/usr/bin:/bin \
        -e MUMA_TEST_PORT_MANAGER="$MUMA_TEST_PORT_MANAGER" \
        -e MUMA_TEST_PORT_LMS="$MUMA_TEST_PORT_LMS" \
        -e API_KEY="${API_KEY:-}" \
        "$BDD_IMAGE" \
        bash -c "pip install --user --quiet --disable-pip-version-check -r tests/bdd/requirements.txt && python -m pytest -p no:warnings tests/bdd/ -v"
fi

echo "--- Gherkin scan-to-listen feature passed ---"
