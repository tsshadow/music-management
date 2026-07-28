#!/bin/bash
# scripts/ci/ultrasonic-build-upload.sh <debug|release>
#
# Builds an Ultrasonic APK and uploads it to apk-hoster, from CI. This is the
# automated equivalent of what used to be a fully manual, local-only step
# (services/ultrasonic/scripts/build.sh + publish.sh + deploy.sh, run by hand).
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

# Ultrasonic's native "Sign in with Google" flow (EditServerFragment.startGoogleSignIn())
# intentionally reuses the SAME Google OAuth Web Client ID already configured for the web
# frontend/backend (GOOGLE_CLIENT_ID) as its Credential Manager `serverClientId`, so the ID
# token it produces has the same audience the backend already verifies against - no separate
# Android OAuth client/SHA-1 registration or extra CI/CD variable is needed. GOOGLE_CLIENT_ID
# itself isn't a plain CI/CD variable but a key inside the PROD_ENV_FILE file-type variable
# (same one release:build-images/deploy:prod already require), so extract it from there.
# NOTE: PROD_ENV_FILE may not be available/set for a debug build on develop (only APK_HOSTER_URL
# is required by .gitlab-ci.yml's ultrasonic:build-debug rule) - fall back to the app's own
# "placeholder-id" default in that case rather than failing the build.
if [ -n "$PROD_ENV_FILE" ] && [ -f "$PROD_ENV_FILE" ]; then
    GOOGLE_WEB_CLIENT_ID=$(grep -E '^GOOGLE_CLIENT_ID=' "$PROD_ENV_FILE" | tail -n1 | cut -d= -f2- | xargs)
fi
if [ -z "$GOOGLE_WEB_CLIENT_ID" ]; then
    echo "Warning: GOOGLE_CLIENT_ID not found in PROD_ENV_FILE; building with Google Sign-In disabled (placeholder client ID)."
fi

# Use a gradle home directory outside the project tree (same pattern as
# scripts/test/ultrasonic-unit.sh) to avoid checkout permission issues, and
# to give each concurrent job slot its own Gradle cache/daemon.
GRADLE_HOME_DIR="/tmp/.gradle_muma_${CI_CONCURRENT_ID:-local}"
mkdir -p "$GRADLE_HOME_DIR"
docker run --rm -v "$GRADLE_HOME_DIR:/gradle_home" alpine chmod -R 777 /gradle_home

fix_permissions() {
    docker run --rm -v "$ROOT_DIR:/workspace" alpine chown -R "$(id -u):$(id -g)" /workspace
}
trap fix_permissions EXIT

# For release builds, write the keystore from the SIGNING_STORE_FILE file-type
# CI/CD variable into the ultrasonic module directory so gradle can find it.
# NOTE: SIGNING_STORE_FILE must hold the keystore *base64-encoded* (a single
# line of plain ASCII), not the raw .jks bytes - GitLab CI/CD variables (even
# file-type ones) are stored/transmitted as text, so raw binary content is not
# guaranteed to round-trip correctly. We base64-decode it here to reconstruct
# the real keystore; this also transparently supports a raw (non-base64) file
# for local/manual testing, since base64 -d simply fails on non-base64 input.
STORE_FILE_NAME=""
if [ "$BUILD_TYPE" == "release" ]; then
    if [ -z "$SIGNING_STORE_FILE" ] || [ ! -f "$SIGNING_STORE_FILE" ]; then
        echo "Error: SIGNING_STORE_FILE (file-type CI/CD variable) is required for release builds."
        exit 1
    fi
    if base64 -d "$SIGNING_STORE_FILE" > "$ROOT_DIR/services/ultrasonic/keystore.jks" 2>/dev/null \
        && [ -s "$ROOT_DIR/services/ultrasonic/keystore.jks" ]; then
        echo "Decoded base64-encoded SIGNING_STORE_FILE into keystore.jks."
    else
        cp "$SIGNING_STORE_FILE" "$ROOT_DIR/services/ultrasonic/keystore.jks"
        echo "SIGNING_STORE_FILE was not base64; copied raw content into keystore.jks."
    fi
    STORE_FILE_NAME="keystore.jks"
fi

# We use a docker image with Android SDK to avoid installing it on the runner
# (same approach as scripts/test/ultrasonic-unit.sh).
docker run --rm \
    -v "$ROOT_DIR:/workspace" \
    -v "$GRADLE_HOME_DIR:/gradle_home" \
    -w "/workspace/services/ultrasonic" \
    -e GRADLE_USER_HOME="/gradle_home" \
    -e SIGNING_STORE_FILE="${STORE_FILE_NAME}" \
    -e SIGNING_STORE_PASSWORD="${SIGNING_STORE_PASSWORD:-dummy}" \
    -e SIGNING_KEY_ALIAS="${SIGNING_KEY_ALIAS:-dummy}" \
    -e SIGNING_KEY_PASSWORD="${SIGNING_KEY_PASSWORD:-dummy}" \
    -e APK_HOSTER_URL="${APK_HOSTER_URL}" \
    -e APK_HOSTER_PASSWORD="${APK_HOSTER_PASSWORD}" \
    -e GOOGLE_WEB_CLIENT_ID="${GOOGLE_WEB_CLIENT_ID}" \
    -e DIST_DIR="dist" \
    mobiledevops/android-sdk-image:latest \
    /bin/bash -c "export ANDROID_SDK_ROOT=\$(find /opt /usr /usr/local -name platforms -type d -print -quit 2>/dev/null | sed 's|/platforms||'); [ -z \"\$ANDROID_SDK_ROOT\" ] && export ANDROID_SDK_ROOT=/opt/android; sdkmanager --sdk_root=\$ANDROID_SDK_ROOT \"build-tools;35.0.0\" \"platforms;android-35\" \"build-tools;34.0.0\" \"platforms;android-34\" && ./scripts/build.sh $BUILD_TYPE && ./scripts/publish.sh $BUILD_TYPE && ./scripts/deploy.sh $BUILD_TYPE"

echo "--- Ultrasonic $BUILD_TYPE build+upload completed ---"
