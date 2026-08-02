#!/bin/bash
# scripts/ci/android-image.sh
# Shared helper: makes sure the project's Android CI image exists, and exports
# ANDROID_CI_IMAGE with its tag. Source it, do not execute it.
#
#   source "$ROOT_DIR/scripts/ci/android-image.sh"
#   docker run --rm -u "$(id -u):$(id -g)" ... "$ANDROID_CI_IMAGE" ...
#
# Both Ultrasonic scripts used to run mobiledevops/android-sdk-image directly,
# as root, re-installing the same SDK packages on every single job and leaving
# root-owned Gradle output behind that broke the *next* job's checkout. The
# image built here has the SDK baked in and owned by the runner's uid, so the
# container never writes as root. See docker/Dockerfile-android-ci.
#
# The tag carries a hash of the Dockerfile, so editing the Dockerfile produces
# a new tag and therefore a rebuild - a fixed tag would silently keep serving
# the stale image forever.

_android_image_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
_android_dockerfile="$_android_image_root/docker/Dockerfile-android-ci"
_android_tag="35-$(sha256sum "$_android_dockerfile" | cut -c1-12)"

ANDROID_CI_IMAGE="music-management/android-ci:${_android_tag}"
export ANDROID_CI_IMAGE

if ! docker image inspect "$ANDROID_CI_IMAGE" >/dev/null 2>&1; then
    echo "--- Building $ANDROID_CI_IMAGE (one-off; the SDK is baked in) ---"
    docker build -f "$_android_dockerfile" \
        --build-arg RUNNER_UID="$(id -u)" \
        --build-arg RUNNER_GID="$(id -g)" \
        -t "$ANDROID_CI_IMAGE" \
        "$_android_image_root/docker/"
fi

unset _android_image_root _android_dockerfile _android_tag
