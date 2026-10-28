#!/bin/bash
# scripts/test/muma-mobile-config-check.sh
# Proves the Gradle side of the build settings (issue #189, step 6), in the CI Android image:
#   1. a debug build configures without MUMA_* variables;
#   2. checkMumaReleaseConfig fails without them;
#   3. it passes with MUMA_SERVER_URL and MUMA_GOOGLE_CLIENT_ID;
#   4. a value with a quote is refused (server URL and own domain).
# Values are placeholders on the documentation domain, never real ones.


ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR" || exit 1
source "$ROOT_DIR/scripts/ci/android-gradle-home.sh"
source "$ROOT_DIR/scripts/ci/android-image.sh"

# One log per run: a fixed /tmp path belongs to whoever wrote it first, and on the shared runner
# that was another user, so the redirect failed and tail printed that user's old output.
LOG_FILE="$(mktemp "${TMPDIR:-/tmp}/muma-config-check.XXXXXX")" || exit 1
trap 'rm -f "$LOG_FILE"' EXIT

gradle_in_image() {
    # Dummy signing values go in by name only, never on argv (bug report 125).
    SIGNING_STORE_PASSWORD=dummy SIGNING_KEY_ALIAS=dummy SIGNING_KEY_PASSWORD=dummy \
    docker run --rm \
        --label "ci.job=${CI_JOB_ID:-local}" \
        -u "$(id -u):$(id -g)" \
        -v "$ROOT_DIR:/workspace" \
        -v "$GRADLE_HOME_DIR:/gradle_home" \
        -w "/workspace/services/muma-mobile" \
        -e GRADLE_USER_HOME="/gradle_home" \
        -e SIGNING_STORE_PASSWORD -e SIGNING_KEY_ALIAS -e SIGNING_KEY_PASSWORD \
        -e MUMA_SERVER_URL -e MUMA_GOOGLE_CLIENT_ID -e MUMA_API_URL -e MUMA_OWN_DOMAIN -e MUMA_ALLOW_DEFAULTS \
        "$ANDROID_CI_IMAGE" \
        /bin/bash -c '. /etc/android-sdk-root && export ANDROID_SDK_ROOT && ./gradlew --console=plain -q "$@"' _ "$@" \
        >"$LOG_FILE" 2>&1
}

fail=0
expect() { # expect <ok|fail> <label> -- gradle args
    local want="$1" label="$2"; shift 3
    gradle_in_image "$@"; local rc=$?
    if { [ "$want" = ok ] && [ $rc -eq 0 ]; } || { [ "$want" = fail ] && [ $rc -ne 0 ]; }; then
        echo "ok: $label"
    else
        echo "FAILED: $label (exit $rc)"; tail -20 "$LOG_FILE"; fail=1
    fi
}

unset MUMA_SERVER_URL MUMA_GOOGLE_CLIENT_ID MUMA_API_URL MUMA_OWN_DOMAIN MUMA_ALLOW_DEFAULTS
expect ok   "debug configures without variables" -- :app:generateDebugBuildConfig
expect fail "release check fails without variables" -- :app:checkMumaReleaseConfig
MUMA_SERVER_URL=https://music.example.org expect fail "release check fails with the default server" -- :app:checkMumaReleaseConfig
MUMA_SERVER_URL=https://lms.example.net MUMA_GOOGLE_CLIENT_ID=abc-123.apps.example expect ok \
    "release check passes with both" -- :app:checkMumaReleaseConfig
MUMA_ALLOW_DEFAULTS=true expect ok "release check passes for an unshipped build" -- :app:checkMumaReleaseConfig
MUMA_SERVER_URL='https://x.example.net"; evil' expect fail "a quote in the value is refused" -- :app:generateDebugBuildConfig
MUMA_OWN_DOMAIN='example.net"; evil' expect fail "a quote in the own domain is refused" -- :app:generateDebugBuildConfig
exit $fail
