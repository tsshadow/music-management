#!/bin/bash
# scripts/test/muma-mobile-detekt.sh
# Static analysis of the Kotlin sources, inside the same Docker image and the
# same Gradle home the unit tests use.
#
# detekt only applies when -Pqc is passed (gradle_scripts/code_quality.gradle),
# which is why it had been sitting in the build unrun: no job passed it, so
# nothing ever failed and nobody noticed. `:app` carried 44 findings and
# `:core:subsonic-api` 30 by the time it was switched on.
#
# Those went into per-module detekt-baseline.xml files at first, so the gate was
# green on the day it was added and red on anything new. By issue #34 most of
# the entries had gone with the legacy UI; the rest were fixed or given a
# targeted @Suppress with its reason, and both baselines were deleted. Every
# finding now fails. Do not regenerate a baseline to get past one: fix it, or
# suppress it on the declaration and say why.
#
# Called from mobile:lint rather than a job of its own, because every
# Android job shares one Gradle home and a second job would queue behind the
# same resource group for no gain.
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

TASK="${1:-detekt}"

echo "--- Running MuMa Mobile detekt ($TASK) ---"

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

echo "--- MuMa Mobile detekt passed ---"
