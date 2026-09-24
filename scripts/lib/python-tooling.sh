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

# Where the installed tooling survives between runs on this host. Every job
# used to `pip install -r requirements-dev.txt` into a throwaway /tmp, so three
# quality jobs per pipeline each pulled the same wheels from PyPI -- and on a
# slow PyPI day (2026-09-18: 80-260 KB/s for an hour) each of them hit the
# ten-minute job timeout. The install now lands in a directory keyed on the
# requirements file and the image, mounted into the container, so only the
# first job after a requirements bump talks to PyPI. The runners are shell
# executors, so $HOME is the runner user's and the cache outlives the job.
# Set PYTHON_TOOLING_CACHE to move it; set it to "none" to install afresh.
TOOLING_CACHE_ROOT="${PYTHON_TOOLING_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/muma-python-tooling}"

# Which requirements files the container installs, space-separated and relative
# to the repository root. The quality jobs only need the linters
# (requirements-dev.txt); the unit and integration suites set this to
# requirements.txt, so they run against the dependency versions the images
# install instead of whatever the runner's system Python happens to carry.
# Each distinct list gets its own cache directory through tooling_cache_key.
TOOLING_REQUIREMENTS="${TOOLING_REQUIREMENTS:-requirements-dev.txt}"

# Extra `docker run` arguments (e.g. --network host) and the names of host
# environment variables to pass into the container. Arrays, set by the caller
# before tooling_container runs.
TOOLING_DOCKER_ARGS=("${TOOLING_DOCKER_ARGS[@]}")
TOOLING_ENV_VARS=("${TOOLING_ENV_VARS[@]}")

# tooling_cache_key
# Sixteen hex characters that change when the requirements or the image do.
# For the default list this is byte-for-byte the key it always was, so existing
# caches on the runners stay valid.
tooling_cache_key() {
    local req
    {
        echo "$TOOLING_IMAGE"
        for req in $TOOLING_REQUIREMENTS; do
            cat "$ROOT_DIR/$req"
        done
    } | sha256sum | cut -c1-16
}

# tooling_container_required
# True when the calling script must run inside the tooling container even if the
# tools are on this host's PATH: in CI (GitLab sets CI=true), or when
# PYTHON_TOOLING_FORCE_CONTAINER=1. The two runners carry different system
# Pythons (LXC 3.11, workstation 3.13) and neither is the 3.14 the images run,
# so a native run would report on an interpreter production never uses -- and
# a different one depending on which runner picked the job up.
tooling_container_required() {
    [ "${PYTHON_TOOLING_CONTAINER:-0}" != "1" ] || return 1
    [ -n "${CI:-}" ] || [ "${PYTHON_TOOLING_FORCE_CONTAINER:-0}" = "1" ]
}

# tooling_use_ci_image
# Switches TOOLING_IMAGE to docker/Dockerfile.python-ci -- python:3.14-slim plus
# the git and ssh client the test suite shells out to -- building it on this
# host first when the tag is missing. Same shape as scripts/ci/cpp-tidy-image.sh:
# the tag carries a hash of the Dockerfile, so editing it forces a rebuild. An
# explicit PYTHON_TOOLING_IMAGE still wins.
tooling_use_ci_image() {
    if [ -n "${PYTHON_TOOLING_IMAGE:-}" ]; then
        return 0
    fi
    local dockerfile="$ROOT_DIR/docker/Dockerfile.python-ci"
    TOOLING_IMAGE="music-management/python-ci:314-$(sha256sum "$dockerfile" | cut -c1-12)-u$(id -u)"
    if ! docker image inspect "$TOOLING_IMAGE" >/dev/null 2>&1; then
        echo "--- Building $TOOLING_IMAGE (one-off per Dockerfile change) ---"
        docker build -q -f "$dockerfile" \
            --build-arg RUNNER_UID="$(id -u)" \
            --build-arg RUNNER_GID="$(id -g)" \
            -t "$TOOLING_IMAGE" "$ROOT_DIR/docker/" >/dev/null
    fi
}

# tooling_mounts
# Prints the `-v` arguments for the tooling and pip-cache directories, one per
# line, or nothing when the cache is off or the host directory cannot be made.
# In the latter case the container falls back to its own /tmp, exactly as before.
tooling_mounts() {
    if [ "$TOOLING_CACHE_ROOT" = "none" ]; then
        return 0
    fi
    local key dir
    key="$(tooling_cache_key)"
    dir="$TOOLING_CACHE_ROOT/$key"
    if ! mkdir -p "$dir" "$TOOLING_CACHE_ROOT/pip-cache" 2>/dev/null; then
        echo "--- Tooling cache $TOOLING_CACHE_ROOT is not writable; installing into the container ---" >&2
        return 0
    fi
    # Every requirements bump (Renovate does one most months) leaves the previous
    # key behind, ~100 MB each. Drop the ones nothing has touched in a month; the
    # name pattern keeps this away from anything that is not a key directory.
    find "$TOOLING_CACHE_ROOT" -mindepth 1 -maxdepth 1 -type d -regextype posix-extended \
        -regex '.*/[0-9a-f]{16}' ! -name "$key" -mtime +30 -exec rm -rf {} + 2>/dev/null || true
    printf -- '-v\n%s:/tmp/tooling\n-v\n%s:/tmp/pip-cache\n' "$dir" "$TOOLING_CACHE_ROOT/pip-cache"
}

# tooling_container <bash -c command>
# Runs one command inside the tooling container with the tools installed (or
# found in the cache) first. The repository is mounted at /repo and the
# container runs as the host user, so nothing root-owned is left behind.
tooling_container() {
    local mounts=()
    local env_args=()
    local name line
    while IFS= read -r line; do
        [ -n "$line" ] && mounts+=("$line")
    done < <(tooling_mounts)
    for name in "${TOOLING_ENV_VARS[@]}"; do
        env_args+=(-e "$name")
    done
    docker run --rm \
        --user "$(id -u):$(id -g)" \
        -v "$ROOT_DIR:/repo" \
        "${mounts[@]}" \
        "${env_args[@]}" \
        "${TOOLING_DOCKER_ARGS[@]}" \
        -e TOOLING_REQUIREMENTS="$TOOLING_REQUIREMENTS" \
        -w /repo \
        -e HOME=/tmp \
        -e PYTHONUSERBASE=/tmp/tooling \
        -e PIP_CACHE_DIR=/tmp/pip-cache \
        -e PATH=/tmp/tooling/bin:/usr/local/bin:/usr/bin:/bin \
        -e PYTHON_TOOLING_CONTAINER=1 \
        "$TOOLING_IMAGE" \
        bash -c "bash scripts/lib/python-tooling-install.sh && $1"
}

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

    echo "--- Running $script inside $TOOLING_IMAGE ---"
    tooling_container "$script $*"
    exit $?
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
    tooling_container "$(printf '%q ' "$@")"
}
