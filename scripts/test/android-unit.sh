#!/bin/bash
# scripts/test/android-unit.sh
# Runs the Ultrasonic JVM unit tests (no emulator required).
# Usage: ./scripts/test/android-unit.sh [gradle-args...]

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ULTRASONIC_DIR="$ROOT_DIR/services/ultrasonic"

cd "$ULTRASONIC_DIR"

echo "--- Running Ultrasonic JVM unit tests ---"
./gradlew test "$@"
