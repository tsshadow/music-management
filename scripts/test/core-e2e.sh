#!/bin/bash
# scripts/test/core-e2e.sh
# Scan to listen, end to end: start the stack, put a track in the music volume,
# scan it, ask for it over the Subsonic API the way the mobile app does, and
# scrobble it until music-manager matches the listen back to the track.
#
# Every other suite proves one component. This is the only one that proves the
# chain.
#
# It ran manually for a while on the assumption that a full stack is expensive.
# Measured, it is about 35 seconds: three containers over an empty database and
# a single fixture track, with the image build the largest part of it. So
# muma:e2e runs on every pipeline and gates.
#
# The chain is written as Gherkin -- tests/bdd/features/scan_to_listen.feature,
# with pytest-bdd steps under it. It was piloted next to a plain pytest function
# saying the same thing, and won on one point: the places where the coverage is
# thinner than the name suggests are written between the steps, in the same
# document as the claims, instead of in a code comment. The plain version is
# gone; keeping both would have meant keeping them in sync forever.
#
# Usage: ./scripts/test/core-e2e.sh
#
# The runners have pytest and requests in their system Python but not
# pytest-bdd, and this repository cannot install into that Python -- python3-venv
# is not there either, so `python3 -m venv` fails on ensurepip. So when the
# plugin is missing the suite runs inside the tooling image instead: the same
# fallback scripts/lint.sh uses, with --network host added because the stack
# publishes its ports on the host and the steps reach them over 127.0.0.1. It
# costs about four seconds over a native run.
#
# What it does NOT cover, and it is worth being blunt about it: nothing here
# runs the Android app. The 6.21.0 startup crash (docs/bug-reports/029) lived
# only in an R8-minified release build, and no test on this machine can execute
# one -- the runner LXC has no /dev/kvm, so there is no emulator. Catching that
# class of bug needs the emulator step, which is the next phase and is a
# resource decision rather than a code one.

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BDD_IMAGE="${PYTHON_TOOLING_IMAGE:-python:3.11-slim}"

# shellcheck source=scripts/lib/e2e-stack.sh
source "$ROOT_DIR/scripts/lib/e2e-stack.sh"

e2e_stack_up muma-e2e

echo "--- Running the scan-to-listen chain ---"
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
        -e MUMA_TEST_LMS_USER="$MUMA_TEST_LMS_USER" \
        -e MUMA_TEST_LMS_PASSWORD="$MUMA_TEST_LMS_PASSWORD" \
        -e MUMA_TEST_FIXTURE_DIR="$MUMA_TEST_FIXTURE_DIR" \
        -e API_KEY="${API_KEY:-}" \
        "$BDD_IMAGE" \
        bash -c "pip install --user --quiet --disable-pip-version-check -r tests/bdd/requirements.txt && python -m pytest -p no:warnings tests/bdd/ -v"
fi

echo "--- Scan-to-listen chain passed ---"
