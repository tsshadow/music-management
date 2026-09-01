#!/bin/bash
# scripts/lib/python-tooling.sh
#
# Shared by scripts/lint.sh and scripts/typecheck.sh.
#
# The CI runner is a shell runner with a bare system Python: ruff, pylint and
# mypy are not installed there and this repository cannot install into it. Same
# approach as scripts/test/muma-server-unit.sh takes for the C++ toolchain -- run inside
# a container that has the dependencies, which only needs a working Docker
# daemon on the host.
#
# On a developer machine the tools are usually already on PATH (see
# requirements-dev.txt), in which case nothing is containerised.
#
# The container runs as the host user with pip installing into /tmp, so no
# root-owned files are left in the workspace. That matters: root-owned build
# output is what the pre_get_sources_script hook in .gitlab-ci.yml exists to
# clean up after.
#
# PYTHONUSERBASE rather than PIP_TARGET: PIP_TARGET is inherited by every pip
# pip-audit runs inside its own throwaway virtualenvs, which redirected those
# installs on top of the tooling directory and deleted pip-audit itself part
# way through the run.

# Tracks the Python the service images run (docker/Dockerfile.*), which is what
# makes a finding here a finding about production rather than about this file.
#
# It was pinned to 3.11 while the images were, and the pin outlived them: the
# images moved to 3.14 and this did not. That is not cosmetic drift. pip-audit
# resolves each requirements file in a throwaway virtualenv built from *this*
# interpreter, so `librosa~=1.0.0` (Requires-Python >=3.12) could not be
# resolved at all and three of the five files failed to audit -- reported as
# "No matching distribution found for librosa", which reads like a bad pin and
# is not. The job is allow_failure, so it stayed red without being read.
#
# The reason it was 3.11 originally -- numpy~=2.0.2 shipping no wheel for 3.13 --
# went away with the same bump: requirements.txt is on numpy~=2.5.2, which
# itself needs >=3.12. Move this with docker/Dockerfile.*, not on its own.
TOOLING_IMAGE="${PYTHON_TOOLING_IMAGE:-python:3.14-slim}"

# rerun_in_container <script-relative-path> [args...]
# Re-executes the calling script inside the tooling container. Never returns.
rerun_in_container() {
    local script="$1"
    shift

    if ! command -v docker >/dev/null 2>&1; then
        echo "Python tooling is missing and Docker is not available." >&2
        echo "Install it with: pip install -r requirements-dev.txt" >&2
        exit 1
    fi

    echo "--- Tooling not on PATH; running $script inside $TOOLING_IMAGE ---"
    exec docker run --rm \
        --user "$(id -u):$(id -g)" \
        -v "$ROOT_DIR:/repo" \
        -w /repo \
        -e HOME=/tmp \
        -e PYTHONUSERBASE=/tmp/tooling \
        -e PIP_CACHE_DIR=/tmp/pip-cache \
        -e PATH=/tmp/tooling/bin:/usr/local/bin:/usr/bin:/bin \
        -e PYTHON_TOOLING_CONTAINER=1 \
        "$TOOLING_IMAGE" \
        bash -c "pip install --user --quiet --disable-pip-version-check -r requirements-dev.txt && $script $*"
}

# have_tool <module-or-binary>
have_tool() {
    command -v "$1" >/dev/null 2>&1 || python3 -m "$1" --version >/dev/null 2>&1
}

# run_python_tool <binary> [args...]
# Runs one Python tool, natively when it is on PATH and otherwise inside the
# tooling container. Unlike rerun_in_container this returns, so a script can mix
# containerised Python tooling with host tools such as npm.
run_python_tool() {
    if command -v "$1" >/dev/null 2>&1; then
        "$@"
        return $?
    fi
    if ! command -v docker >/dev/null 2>&1; then
        echo "$1 is missing and Docker is not available." >&2
        return 127
    fi
    docker run --rm \
        --user "$(id -u):$(id -g)" \
        -v "$ROOT_DIR:/repo" \
        -w /repo \
        -e HOME=/tmp \
        -e PYTHONUSERBASE=/tmp/tooling \
        -e PIP_CACHE_DIR=/tmp/pip-cache \
        -e PATH=/tmp/tooling/bin:/usr/local/bin:/usr/bin:/bin \
        "$TOOLING_IMAGE" \
        bash -c "pip install --user --quiet --disable-pip-version-check -r requirements-dev.txt >/dev/null && $(printf '%q ' "$@")"
}
