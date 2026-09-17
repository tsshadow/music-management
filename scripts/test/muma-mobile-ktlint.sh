#!/bin/bash
# scripts/test/muma-mobile-ktlint.sh
# Kotlin formatting, inside the same Docker image and Gradle home the unit
# tests use.
#
# ktlint is the third checker that was fully configured here and invoked by
# nothing: the plugin is applied in gradle_scripts/code_quality.gradle behind
# -Pqc, exactly like detekt was before it was wired up, and Android Lint before
# that. The tree had drifted to 238 files needing reformatting.
#
# Unlike detekt and Android Lint this one gets no baseline, because ktlintFormat
# fixes what it finds: the whole-tree pass left a single violation, suppressed
# at the file that earned it. A baseline would only hide the next drift.
#
# Fix a failure with:
#
#   ./scripts/test/muma-mobile-ktlint.sh ktlintFormat
#
# Called from muma-mobile:check rather than a job of its own, because every
# Android job shares one Gradle home and a second job would queue behind the
# same resource group for no gain.
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

TASK="${1:-ktlintCheck}"

echo "--- Running MuMa Mobile ktlint ($TASK) ---"

source "$ROOT_DIR/scripts/ci/android-gradle-home.sh"
source "$ROOT_DIR/scripts/ci/android-image.sh"

docker run --rm \
    --label "ci.job=${CI_JOB_ID:-local}" \
    -u "$(id -u):$(id -g)" \
    -v "$ROOT_DIR:/workspace" \
    -v "$GRADLE_HOME_DIR:/gradle_home" \
    -w "/workspace/services/muma-mobile" \
    -e GRADLE_USER_HOME="/gradle_home" \
    -e SIGNING_STORE_PASSWORD=dummy \
    -e SIGNING_KEY_ALIAS=dummy \
    -e SIGNING_KEY_PASSWORD=dummy \
    "$ANDROID_CI_IMAGE" \
    /bin/bash -c ". /etc/android-sdk-root && export ANDROID_SDK_ROOT && ./gradlew -Pqc $TASK"

echo "--- MuMa Mobile ktlint passed ---"
