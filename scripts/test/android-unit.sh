#!/bin/bash
# scripts/test/android-unit.sh
# Runs the MuMa Mobile JVM unit tests (no emulator required).
# Usage: ./scripts/test/android-unit.sh [gradle-args...]

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MUMA_MOBILE_DIR="$ROOT_DIR/services/muma-mobile"

cd "$MUMA_MOBILE_DIR"

echo "--- Running MuMa Mobile JVM unit tests ---"
./gradlew test "$@"
