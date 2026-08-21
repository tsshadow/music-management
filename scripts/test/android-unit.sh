#!/bin/bash
# scripts/test/android-unit.sh
# Runs the MuMa Mobile JVM unit tests (no emulator required).
# Usage: ./scripts/test/android-unit.sh [gradle-args...]
#
#   ./scripts/test/android-unit.sh
#   ./scripts/test/android-unit.sh --tests "nl.teunschriks.mumamobile.wizard.WizardPlanTest"
#
# This used to call ./gradlew on the host, which needs an Android SDK and a
# local.properties pointing at it. Neither is present on a fresh checkout or in
# a git worktree (local.properties is gitignored), so the script failed with
# "SDK location not found" before running a single test. It now runs in the same
# image CI uses, which has the SDK baked in, and forwards its arguments to
# Gradle so a single test class can be run without building the whole report.

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "--- Running MuMa Mobile JVM unit tests ---"

source "$ROOT_DIR/scripts/ci/android-gradle-home.sh"
source "$ROOT_DIR/scripts/ci/android-image.sh"

docker run --rm \
    -u "$(id -u):$(id -g)" \
    -v "$ROOT_DIR:/workspace" \
    -v "$GRADLE_HOME_DIR:/gradle_home" \
    -w "/workspace/services/muma-mobile" \
    -e GRADLE_USER_HOME="/gradle_home" \
    -e SIGNING_STORE_PASSWORD=dummy \
    -e SIGNING_KEY_ALIAS=dummy \
    -e SIGNING_KEY_PASSWORD=dummy \
    "$ANDROID_CI_IMAGE" \
    /bin/bash -c '. /etc/android-sdk-root && export ANDROID_SDK_ROOT && ./gradlew :app:testDebugUnitTest "$@"' _ "$@"
