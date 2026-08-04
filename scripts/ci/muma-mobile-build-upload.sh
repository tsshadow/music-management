#!/bin/bash
# scripts/ci/muma-mobile-build-upload.sh <debug|release>
#
# Builds an MuMa Mobile APK and uploads it to apk-hoster, from CI. This is the
# automated equivalent of what used to be a fully manual, local-only step
# (services/muma-mobile/scripts/build.sh + publish.sh + deploy.sh, run by hand).
#
# Required CI/CD variables (see docs/deployment.md):
#   - APK_HOSTER_URL, APK_HOSTER_PASSWORD: always required.
#   - SIGNING_STORE_FILE (file-type variable with the keystore),
#     SIGNING_STORE_PASSWORD, SIGNING_KEY_ALIAS, SIGNING_KEY_PASSWORD:
#     only required for "release" builds (debug builds are unsigned/dev-signed).
#
# Jobs calling this script are gated (in .gitlab-ci.yml) on these variables
# being present, so the pipeline never fails merely because they haven't been
# configured yet - it just skips the job.

set -e

BUILD_TYPE=$(echo "${1:-debug}" | tr '[:upper:]' '[:lower:]')
if [[ "$BUILD_TYPE" != "release" && "$BUILD_TYPE" != "debug" ]]; then
    echo "Usage: $0 <debug|release>"
    exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [ -z "$APK_HOSTER_URL" ] || [ -z "$APK_HOSTER_PASSWORD" ]; then
    echo "Error: APK_HOSTER_URL / APK_HOSTER_PASSWORD are not set. See docs/deployment.md."
    exit 1
fi

# MuMa Mobile's native "Sign in with Google" flow (EditServerFragment.startGoogleSignIn())
# intentionally reuses the SAME Google OAuth Web Client ID already configured for the web
# frontend/backend (GOOGLE_CLIENT_ID) as its Credential Manager `serverClientId`, so the ID
# token it produces has the same audience the backend already verifies against - no separate
# Android OAuth client/SHA-1 registration or extra CI/CD variable is needed. GOOGLE_CLIENT_ID
# itself isn't a plain CI/CD variable but a key inside the PROD_ENV_FILE file-type variable
# (same one release:build-images/deploy:prod already require), so extract it from there.
# NOTE: PROD_ENV_FILE may not be available/set for a debug build on develop (only APK_HOSTER_URL
# is required by .gitlab-ci.yml's muma-mobile:build-debug rule) - fall back to the app's own
# "placeholder-id" default in that case rather than failing the build.
if [ -n "$PROD_ENV_FILE" ] && [ -f "$PROD_ENV_FILE" ]; then
    GOOGLE_WEB_CLIENT_ID=$(grep -E '^GOOGLE_CLIENT_ID=' "$PROD_ENV_FILE" | tail -n1 | cut -d= -f2- | xargs)
fi
if [ -z "$GOOGLE_WEB_CLIENT_ID" ]; then
    echo "Warning: GOOGLE_CLIENT_ID not found in PROD_ENV_FILE; building with Google Sign-In disabled (placeholder client ID)."
fi

# Use a gradle home directory outside the project tree (same pattern as
# scripts/test/muma-mobile-unit.sh) to avoid checkout permission issues, and
# to give each concurrent job slot its own Gradle cache/daemon.
GRADLE_HOME_DIR="/tmp/.gradle_muma_${CI_CONCURRENT_ID:-local}"
mkdir -p "$GRADLE_HOME_DIR"

# A runner that ran the older, root-in-container version of this script still
# has a root-owned Gradle home from back then, which the container - now the
# host user - cannot write to. Hand it over once, via a throwaway root
# container, so the switch does not need a manual cleanup on every runner.
if [ -n "$(find "$GRADLE_HOME_DIR" ! -user "$(id -u)" -print -quit 2>/dev/null)" ]; then
    echo "Reclaiming $GRADLE_HOME_DIR for $(id -un)"
    docker run --rm -v "$GRADLE_HOME_DIR:/gradle_home" alpine chown -R "$(id -u):$(id -g)" /gradle_home
fi

# The build container runs as the host user (see scripts/ci/android-image.sh),
# so there is no chmod 777 pre-step and no chown-back trap: nothing it writes
# is owned by root in the first place.
source "$ROOT_DIR/scripts/ci/android-image.sh"

# Write the keystore from the SIGNING_STORE_FILE file-type CI/CD variable into
# the app module directory so gradle can find it.
# NOTE: SIGNING_STORE_FILE must hold the keystore *base64-encoded* (a single
# line of plain ASCII), not the raw .jks bytes - GitLab CI/CD variables (even
# file-type ones) are stored/transmitted as text, so raw binary content is not
# guaranteed to round-trip correctly. We base64-decode it here to reconstruct
# the real keystore; this also transparently supports a raw (non-base64) file
# for local/manual testing, since base64 -d simply fails on non-base64 input.
#
# The keystore is written for DEBUG builds too whenever it is available (see
# build.gradle's `debug { initWith signingConfigs.release }`). Without it, a CI
# debug APK is signed with the throwaway debug keystore that the Android SDK
# docker image generates on the fly - a different signing certificate on every
# single build. Google's Credential Manager only issues a credential to an app
# whose package name + certificate SHA-1 match a registered Android-type OAuth
# client (bug report 011), so with a per-build random certificate "Sign in with
# Google" can never work on a CI debug APK. Signing debug builds with the same,
# stable keystore makes that SHA-1 registerable once (see docs/deployment.md).
# It is still only *required* for release builds.
STORE_FILE_NAME=""
if [ "$BUILD_TYPE" == "release" ]; then
    if [ -z "$SIGNING_STORE_FILE" ] || [ ! -f "$SIGNING_STORE_FILE" ]; then
        echo "Error: SIGNING_STORE_FILE (file-type CI/CD variable) is required for release builds."
        exit 1
    fi
    if [ -z "$SIGNING_STORE_PASSWORD" ]; then
        echo "Error: SIGNING_STORE_PASSWORD is required for release builds."
        exit 1
    fi
fi
# A keystore without its password is useless (and would make gradle fail on the debug build
# rather than silently fall back), so both must be present before we write it out.
if [ -n "$SIGNING_STORE_FILE" ] && [ -f "$SIGNING_STORE_FILE" ] && [ -n "$SIGNING_STORE_PASSWORD" ]; then
    if base64 -d "$SIGNING_STORE_FILE" > "$ROOT_DIR/services/muma-mobile/keystore.jks" 2>/dev/null \
        && [ -s "$ROOT_DIR/services/muma-mobile/keystore.jks" ]; then
        echo "Decoded base64-encoded SIGNING_STORE_FILE into keystore.jks."
    else
        cp "$SIGNING_STORE_FILE" "$ROOT_DIR/services/muma-mobile/keystore.jks"
        echo "SIGNING_STORE_FILE was not base64; copied raw content into keystore.jks."
    fi
    STORE_FILE_NAME="keystore.jks"
elif [ "$BUILD_TYPE" == "debug" ]; then
    echo "Warning: SIGNING_STORE_FILE not available; this debug APK gets a throwaway signing"
    echo "         certificate and its 'Sign in with Google' will fail (see bug report 020)."
fi

# Project-owned Android SDK image, same as scripts/test/muma-mobile-unit.sh.
docker run --rm \
    -u "$(id -u):$(id -g)" \
    -v "$ROOT_DIR:/workspace" \
    -v "$GRADLE_HOME_DIR:/gradle_home" \
    -w "/workspace/services/muma-mobile" \
    -e GRADLE_USER_HOME="/gradle_home" \
    -e SIGNING_STORE_FILE="${STORE_FILE_NAME}" \
    -e SIGNING_STORE_PASSWORD="${SIGNING_STORE_PASSWORD:-dummy}" \
    -e SIGNING_KEY_ALIAS="${SIGNING_KEY_ALIAS:-dummy}" \
    -e SIGNING_KEY_PASSWORD="${SIGNING_KEY_PASSWORD:-dummy}" \
    -e APK_HOSTER_URL="${APK_HOSTER_URL}" \
    -e APK_HOSTER_PASSWORD="${APK_HOSTER_PASSWORD}" \
    -e GOOGLE_WEB_CLIENT_ID="${GOOGLE_WEB_CLIENT_ID}" \
    -e DIST_DIR="dist" \
    "$ANDROID_CI_IMAGE" \
    /bin/bash -c ". /etc/android-sdk-root && export ANDROID_SDK_ROOT && ./scripts/build.sh $BUILD_TYPE && ./scripts/publish.sh $BUILD_TYPE && ./scripts/deploy.sh $BUILD_TYPE"

echo "--- MuMa Mobile $BUILD_TYPE build+upload completed ---"
