#!/bin/bash
# scripts/test/muma-server-tidy.sh
# clang-tidy over the MuMa Server sources, against the .clang-tidy that has
# been in services/music-management-server/ being read by nothing.
#
# This is the server's second static check, after clang-format. Unlike
# clang-format it analyses code rather than layout, so it needs a compilation
# database: which flags each translation unit is compiled with, which headers
# it sees. That is what the cmake configure below produces, and it is why this
# cannot be a two-line container invocation the way the formatter is.
#
# Cost, measured 2026-09-01: 307 translation units, ~15s each single-threaded,
# so ~10 minutes at -j16 with memory to spare. That is why it is
# `changes:`-gated on the server sources and not run on every pipeline. See the
# parallelism block below for why the -j is not simply nproc.
#
# UNITY_BUILD=OFF matters. The shipped images merge many .cpp files into one
# translation unit; clang-tidy would then report against the merged file and
# the paths would not exist. The same switch is why the coverage build turns
# unity off (see Dockerfile-build-alpine).
#
# Findings are baselined in security/accepted-clang-tidy-findings.txt: 1540 on
# the day this was wired, so gating on zero was never an option. Green today,
# red on anything new -- the same contract detekt, Android Lint and semgrep
# have here.
#
# Usage: ./scripts/test/muma-server-tidy.sh                  # check
#        ./scripts/test/muma-server-tidy.sh --write-baseline # accept current
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVER_DIR="$ROOT_DIR/services/music-management-server"
BASELINE="$ROOT_DIR/security/accepted-clang-tidy-findings.txt"
LOG="$ROOT_DIR/clang-tidy.log"

MODE=check
[ "${1:-}" = "--write-baseline" ] && MODE="write"

# shellcheck source=scripts/ci/cpp-tidy-image.sh
source "$ROOT_DIR/scripts/ci/cpp-tidy-image.sh"

# Parallelism is bounded by memory, and the sum is done HERE rather than inside
# the container, because /proc/meminfo is not namespaced. On the runner LXC the
# host correctly reports 15GB while a container on it reads 30GB -- it sees
# straight past the LXC's limit to the Proxmox node. Computing this inside the
# container picked -j15 where -j7 was the honest answer, and the job was killed
# at 45 minutes for the second time.
#
# Each clang-tidy process pulls in boost and Wt headers and comfortably passes
# 1GB, so budget 2GB and take the lower of the two limits:
#
#   workstation  16 cores, 31GB  ->  -j15, 10 minutes
#   runner LXC   20 cores, 15GB  ->  -j7
# TIDY_JOBS can be set to override, which is how the -j7 the LXC gets was
# timed on a machine that is not the LXC.
TIDY_CORES=$(nproc)
TIDY_MEM_GB=$(awk '/MemTotal/ {print int($2 / 1024 / 1024)}' /proc/meminfo)
if [ -z "${TIDY_JOBS:-}" ]; then
    TIDY_JOBS=$((TIDY_MEM_GB / 2))
    [ "$TIDY_JOBS" -lt 2 ] && TIDY_JOBS=2
    [ "$TIDY_JOBS" -gt "$TIDY_CORES" ] && TIDY_JOBS=$TIDY_CORES
fi

echo "--- Running clang-tidy over the MuMa Server sources ---"
echo "--- Host: ${TIDY_CORES} cores, ${TIDY_MEM_GB}GB -> -j${TIDY_JOBS} ---"

docker run --rm \
    -u "$(id -u):$(id -g)" \
    -v "$SERVER_DIR:/src" \
    -v "$ROOT_DIR:/repo" \
    -w /src \
    -e TIDY_JOBS="$TIDY_JOBS" \
    "$CPP_TIDY_IMAGE" \
    sh -c '
set -e
clang-tidy --version | head -2

# Out of the source tree: /src is a bind mount, and a build directory left in
# it would be picked up by the next checkout and by clang-format alike.
cmake -S /src -B /tmp/tidybuild \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
    -DCMAKE_UNITY_BUILD=OFF \
    -DCMAKE_BUILD_TYPE=Debug \
    -DBUILD_TESTING=OFF \
    -DBUILD_BENCHMARKS=OFF >/tmp/cmake.log 2>&1 || { tail -30 /tmp/cmake.log; exit 1; }

echo "--- $(python3 -c "import json;print(len(json.load(open(\"/tmp/tidybuild/compile_commands.json\"))))") translation units, -j${TIDY_JOBS} ---"

# run-clang-tidy exits non-zero whenever it emitted anything; the baseline
# decides pass or fail, so its status is not the answer here.
run-clang-tidy -p /tmp/tidybuild -j "$TIDY_JOBS" -quiet >/repo/clang-tidy.log 2>&1 || true
'

echo "--- Comparing against the baseline ---"
if [ "$MODE" = write ]; then
    python3 "$ROOT_DIR/scripts/ci/clang_tidy_baseline.py" write "$LOG" "$BASELINE" /src
    rm -f "$LOG"
    exit 0
fi

status=0
python3 "$ROOT_DIR/scripts/ci/clang_tidy_baseline.py" check "$LOG" "$BASELINE" /src || status=$?
rm -f "$LOG"
[ "$status" -eq 0 ] && echo "--- MuMa Server clang-tidy OK ---"
exit "$status"
