#!/bin/bash
# scripts/ci/create-release-tags.sh
#
# Runs on `master` after a release/* or hotfix/* branch has been merged. Both
# are treated identically: what is tagged is whatever VERSION says on master,
# so the hotfix path needs no special case here.
# Creates the immutable, CI-only git tags that make master's history the
# trustworthy "what's actually been released" record:
#   - release-vX.Y.Z         always, from the root VERSION file.
#   - muma-mobile-vX.Y.Z      only if this merge also bumped MuMa Mobile's own
#                            versionName (i.e. this release included an
#                            official MuMa Mobile build).
#
# Tags are never created manually - only here, only on master, so "what's
# live" can always be answered by looking at master's latest tags. See
# docs/release-management.md for the full policy.

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [ -z "$TAG_CREATION_TOKEN" ]; then
    echo "Error: TAG_CREATION_TOKEN CI/CD variable is not set. See docs/deployment.md."
    exit 1
fi

create_tag() {
    local tag_name="$1"
    local message="$2"

    if curl -sf --header "PRIVATE-TOKEN: ${TAG_CREATION_TOKEN}" \
        "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/repository/tags/${tag_name}" >/dev/null 2>&1; then
        echo "Tag $tag_name already exists, skipping."
        return 0
    fi

    echo "Creating tag $tag_name at ${CI_COMMIT_SHA}..."
    curl -sf --request POST --header "PRIVATE-TOKEN: ${TAG_CREATION_TOKEN}" \
        --data-urlencode "tag_name=${tag_name}" \
        --data-urlencode "ref=${CI_COMMIT_SHA}" \
        --data-urlencode "message=${message}" \
        "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/repository/tags"
    echo ""
    echo "Created tag $tag_name."
}

BACKEND_VERSION=$(cat VERSION)
create_tag "release-v${BACKEND_VERSION}" "Backend/monorepo release v${BACKEND_VERSION}"

# Only tag MuMa Mobile separately if its own versionName actually changed as
# part of the commit(s) that just landed on master (i.e. this release cycle
# included an official MuMa Mobile release, per the debug-on-develop /
# official-on-release policy).
PARENT_SHA=$(git rev-parse "${CI_COMMIT_SHA}^1" 2>/dev/null || echo "")
if [ -n "$PARENT_SHA" ] && ! git diff --quiet "$PARENT_SHA" "${CI_COMMIT_SHA}" -- services/muma-mobile/app/build.gradle 2>/dev/null; then
    MUMA_MOBILE_VERSION=$(grep "versionName" services/muma-mobile/app/build.gradle | head -n 1 | sed 's/.*"\(.*\)".*/\1/')
    create_tag "muma-mobile-v${MUMA_MOBILE_VERSION}" "MuMa Mobile release v${MUMA_MOBILE_VERSION}"
else
    echo "MuMa Mobile build.gradle unchanged in this merge - no separate muma-mobile tag needed."
fi
