#!/bin/bash
# scripts/ci/muma-mobile-build-upload.sh <debug|release>
#
# Builds an MuMa Mobile APK and uploads it to apk-hoster, from CI. This is the
# automated equivalent of what used to be a fully manual, local-only step
# (services/muma-mobile/scripts/build.sh + publish.sh + deploy.sh, run by hand).
#
# Required CI/CD variables (see docs/deployment.md):
#   - APK_HOSTER_URL, APK_HOSTER_PASSWORD: always required. The password is read only by
#     scripts/deploy.sh for the upload; app/build.gradle no longer compiles it into the APK
#     (bug report 054), so it must never be added back as a BuildConfig field.
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
cd "$ROOT_DIR" || exit 1

if [ -z "$APK_HOSTER_URL" ] || [ -z "$APK_HOSTER_PASSWORD" ]; then
    echo "Error: APK_HOSTER_URL / APK_HOSTER_PASSWORD are not set. See docs/deployment.md."
    exit 1
fi

# The server address and the Google OAuth Web client id are compiled into the APK from the CI/CD
# variables MUMA_SERVER_URL and MUMA_GOOGLE_CLIENT_ID, plus MUMA_API_URL (a separate host for the
# MuMa API) and MUMA_OWN_DOMAIN (the owner's domain: servers on it route to that API).
# app/build.gradle reads them from the environment as the Gradle properties muma.serverUrl,
# muma.googleClientId, muma.apiUrl and muma.ownDomain; no value goes on a command line (bug
# report 125). The Google client id is the same Web client the backend verifies (GOOGLE_CLIENT_ID),
# so the ID token has an audience the backend accepts.
# A build that lacks them gets the neutral defaults (https://music.example.org, no Google button).
# That is fine for a debug build and wrong for a release, so a release stops here instead.
if [ "$BUILD_TYPE" == "release" ]; then
    # The owner's release must route to his API: without MUMA_API_URL and MUMA_OWN_DOMAIN an
    # install with an older server address would fall back to <server>/muma. Gradle keeps both
    # optional, so a public build can use the default.
    for required in MUMA_SERVER_URL MUMA_GOOGLE_CLIENT_ID MUMA_API_URL MUMA_OWN_DOMAIN; do
        if [ -z "${!required}" ]; then
            echo "Error: $required is not set. A release without it would ship the neutral default (see docs/designs/public-edition/)." >&2
            exit 1
        fi
    done
elif [ -z "$MUMA_SERVER_URL" ] || [ -z "$MUMA_GOOGLE_CLIENT_ID" ]; then
    echo "Warning: MUMA_SERVER_URL / MUMA_GOOGLE_CLIENT_ID not set; building with the neutral server and without Google Sign-In."
fi

# Gradle home (outside the project tree, to avoid git checkout permission
# issues) plus its one-off root-ownership repair - see the helper for why it
# is shared rather than per concurrent job slot.
source "$ROOT_DIR/scripts/ci/android-gradle-home.sh"

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

# The secrets are exported here and handed to docker as `-e NAME` without a value, which
# copies them from this environment: `-e NAME=value` would put them on docker's argv, readable
# by every account on the shared runner through `ps` (GitLab #40).
export SIGNING_STORE_PASSWORD="${SIGNING_STORE_PASSWORD:-dummy}"
export SIGNING_KEY_ALIAS="${SIGNING_KEY_ALIAS:-dummy}"
export SIGNING_KEY_PASSWORD="${SIGNING_KEY_PASSWORD:-dummy}"
export APK_HOSTER_PASSWORD="${APK_HOSTER_PASSWORD:-}"

# Project-owned Android SDK image, same as scripts/test/muma-mobile-unit.sh.
docker run --rm \
    --label "ci.job=${CI_JOB_ID:-local}" \
    -u "$(id -u):$(id -g)" \
    -v "$ROOT_DIR:/workspace" \
    -v "$GRADLE_HOME_DIR:/gradle_home" \
    -w "/workspace/services/muma-mobile" \
    -e GRADLE_USER_HOME="/gradle_home" \
    -e SIGNING_STORE_FILE="${STORE_FILE_NAME}" \
    -e SIGNING_STORE_PASSWORD \
    -e SIGNING_KEY_ALIAS \
    -e SIGNING_KEY_PASSWORD \
    -e APK_HOSTER_URL="${APK_HOSTER_URL}" \
    -e APK_HOSTER_PASSWORD \
    -e MUMA_SERVER_URL \
    -e MUMA_API_URL \
    -e MUMA_OWN_DOMAIN \
    -e MUMA_GOOGLE_CLIENT_ID \
    -e DIST_DIR="dist" \
    "$ANDROID_CI_IMAGE" \
    /bin/bash -c ". /etc/android-sdk-root && export ANDROID_SDK_ROOT && ./scripts/build.sh $BUILD_TYPE && ./scripts/publish.sh $BUILD_TYPE && ./scripts/deploy.sh $BUILD_TYPE"

echo "--- MuMa Mobile $BUILD_TYPE build+upload completed ---"
