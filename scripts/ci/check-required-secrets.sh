#!/bin/bash
# scripts/ci/check-required-secrets.sh
#
# Verifies that every CI/CD variable a release/* or hotfix/* build needs is set
# and non-empty, BEFORE any image is built.
#
# Rationale: four of these variables gate whole jobs at the `rules:` level
# (release:build-images needs DOCKERHUB_*, mobile:build-release needs
# APK_HOSTER_URL and SIGNING_STORE_FILE). A rules-level check does not fail
# when the variable is missing: the job silently drops out of the pipeline,
# and a skipped job blocks nothing. An expired Docker Hub token would mean a
# tag without images, and a dropped APK variable a release with no APK and
# nothing red anywhere. This job runs on every release/hotfix branch, so the
# absence fails loudly here instead. Per AGENTS.md rule 1 ("Tests required") /
# rule 10 ("contract discipline"), a release pipeline that skips this check is
# not considered passing.
#
# This repository builds and publishes; an installation deploys
# (docs/designs/ops-split/). The production host, its SSH key and its env files
# are the operations repository's variables and are not checked here.

set -e

require_var() {
    # $1: variable name, $2: what silently disappears without it.
    local name="$1" consequence="$2"
    if [ -z "${!name:-}" ]; then
        echo "Missing required secret: CI/CD variable '${name}' is not set. Without it ${consequence}."
        return 1
    fi
    echo "OK: '${name}' is set."
    return 0
}

missing=0

require_var "DOCKERHUB_USERNAME" \
    "release:build-images vanishes and the release is tagged without images" || missing=1
require_var "DOCKERHUB_TOKEN" \
    "release:build-images vanishes and the release is tagged without images" || missing=1
require_var "APK_HOSTER_URL" \
    "mobile:build-release vanishes and the release ships without an APK" || missing=1
require_var "SIGNING_STORE_FILE" \
    "mobile:build-release vanishes and the release ships without an APK" || missing=1

# The player's "Sign in with Google" button is compiled in by release:build-images
# (VITE_GOOGLE_CLIENT_ID, else MUMA_GOOGLE_CLIENT_ID: the same Web client id). Empty,
# Vite removes the button from the bundle and nothing fails.
if [ -n "${VITE_GOOGLE_CLIENT_ID:-}" ]; then
    echo "OK: 'VITE_GOOGLE_CLIENT_ID' is set."
elif [ -n "${MUMA_GOOGLE_CLIENT_ID:-}" ]; then
    echo "OK: the player's Google client id is set as 'MUMA_GOOGLE_CLIENT_ID'."
else
    echo "Missing required secret: neither 'VITE_GOOGLE_CLIENT_ID' nor 'MUMA_GOOGLE_CLIENT_ID' is set." \
        "Without one the player image has no \"Sign in with Google\" button."
    missing=1
fi

# DOCKER_USER, when set, is the registry user the images are named under
# (scripts/ci/release-image-names.sh). They are pushed with the DOCKERHUB_USERNAME
# login, so the two must be the same account.
if [ -n "${DOCKER_USER:-}" ] && [ -n "${DOCKERHUB_USERNAME:-}" ] && [ "$DOCKER_USER" != "$DOCKERHUB_USERNAME" ]; then
    echo "Mismatch: the DOCKER_USER CI/CD variable differs from DOCKERHUB_USERNAME."
    echo "  Images are pushed as DOCKERHUB_USERNAME and named as DOCKER_USER; they must be the same account."
    missing=1
fi

if [ "$missing" -ne 0 ]; then
    echo ""
    echo "One or more required secrets are missing for this release. Fix the CI/CD"
    echo "variables above (Project > Settings > CI/CD > Variables) before re-running"
    echo "this pipeline -- see docs/self-hosting.md."
    exit 1
fi

echo ""
echo "--- All required secrets are present for this release ---"
