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
[ "${1:-}" = "--write-baseline" ] && MODE=write

# shellcheck source=scripts/ci/cpp-tidy-image.sh
source "$ROOT_DIR/scripts/ci/cpp-tidy-image.sh"

echo "--- Running clang-tidy over the MuMa Server sources ---"

docker run --rm \
    -u "$(id -u):$(id -g)" \
    -v "$SERVER_DIR:/src" \
    -v "$ROOT_DIR:/repo" \
    -w /src \
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

# Parallelism is bounded by memory, not by cores. Each clang-tidy process
# analysing this codebase pulls in boost and Wt headers and comfortably passes
# 1GB, so -j$(nproc) is only safe where there is RAM to match:
#
#   workstation  16 cores, 31GB  ->  ~2GB per process, 10 minutes
#   runner LXC   20 cores, 15GB  ->  0.75GB per process, over 30 and killed
#
# More cores, three times slower. Budget 2GB per process and take whichever of
# the two limits is lower.
CORES=$(nproc)
MEM_GB=$(awk "/MemTotal/ {print int(\$2 / 1024 / 1024)}" /proc/meminfo)
JOBS=$(( MEM_GB / 2 ))
[ "$JOBS" -lt 2 ] && JOBS=2
[ "$JOBS" -gt "$CORES" ] && JOBS=$CORES

echo "--- $(python3 -c "import json;print(len(json.load(open(\"/tmp/tidybuild/compile_commands.json\"))))") translation units, -j${JOBS} (${CORES} cores, ${MEM_GB}GB) ---"

# run-clang-tidy exits non-zero whenever it emitted anything; the baseline
# decides pass or fail, so its status is not the answer here.
run-clang-tidy -p /tmp/tidybuild -j "$JOBS" -quiet >/repo/clang-tidy.log 2>&1 || true
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
