#!/bin/bash
# scripts/lib/python-tooling.sh
#
# Shared by scripts/lint.sh and scripts/typecheck.sh.
#
# The CI runner is a shell runner with a bare system Python: ruff, pylint and
# mypy are not installed there and this repository cannot install into it. Same
# approach as scripts/test/lms-unit.sh takes for the C++ toolchain -- run inside
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

TOOLING_IMAGE="${PYTHON_TOOLING_IMAGE:-python:3.13-slim}"

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
        -e PIP_TARGET=/tmp/tooling \
        -e PIP_CACHE_DIR=/tmp/pip-cache \
        -e PYTHONPATH=/tmp/tooling \
        -e PATH=/tmp/tooling/bin:/usr/local/bin:/usr/bin:/bin \
        -e PYTHON_TOOLING_CONTAINER=1 \
        "$TOOLING_IMAGE" \
        bash -c "pip install --quiet --disable-pip-version-check -r requirements-dev.txt && $script $*"
}

# have_tool <module-or-binary>
have_tool() {
    command -v "$1" >/dev/null 2>&1 || python3 -m "$1" --version >/dev/null 2>&1
}
