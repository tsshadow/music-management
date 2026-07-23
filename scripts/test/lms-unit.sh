#!/bin/bash
# scripts/test/lms-unit.sh
# Configures (if needed) and runs the existing upstream CTest/GTest suite for the
# music-management-server (LMS) C++ code.
# Usage: ./scripts/test/lms-unit.sh [ctest-args...]

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LMS_DIR="$ROOT_DIR/services/music-management-server"
BUILD_DIR="${LMS_BUILD_DIR:-$LMS_DIR/build}"

cd "$LMS_DIR"

if [ ! -d "$BUILD_DIR" ]; then
    echo "--- Configuring LMS build directory ($BUILD_DIR) ---"
    cmake -S "$LMS_DIR" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Debug
fi

echo "--- Building LMS test targets ---"
cmake --build "$BUILD_DIR" -j"$(nproc)"

echo "--- Running LMS unit tests (ctest) ---"
ctest --test-dir "$BUILD_DIR" --output-on-failure "$@"
