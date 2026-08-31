#!/bin/bash
# scripts/test/muma-mobile-lint.sh
# Android Lint over the app and, via checkDependencies=true in app/build.gradle,
# every core module it depends on -- inside the same Docker image and Gradle
# home the unit tests use.
#
# Lint was fully configured (baseline, abortOnError, warningsAsErrors) and ran
# nowhere: no CI job invoked it, so the baseline drifted stale and develop sat
# at 98 unfiltered errors that nothing ever surfaced. Same story as detekt
# before it -- a checker that is configured but not wired to a job does not
# exist.
#
# The pre-existing findings live in app/lint-baseline.xml, regenerated the day
# this gate was wired: green today, red on anything new. Shrink it by fixing
# findings and regenerating:
#
#   ./scripts/test/muma-mobile-lint.sh updateLintBaseline
#
# Called from muma-mobile:check rather than a job of its own, because every
# Android job shares one Gradle home and a second job would queue behind the
# same resource group for no gain.
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

TASK="${1:-:app:lintDebug}"

echo "--- Running MuMa Mobile Android Lint ($TASK) ---"

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
    /bin/bash -c ". /etc/android-sdk-root && export ANDROID_SDK_ROOT && ./gradlew $TASK"

echo "--- MuMa Mobile Android Lint passed ---"
