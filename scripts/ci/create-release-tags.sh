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
# muma-ops docs/release-management.md for the full policy.
# The token goes to curl through a process substitution (`--header @<(...)`), never as
# `--header "PRIVATE-TOKEN: $TOKEN"`: a command line is readable by every account on the
# shell-executor runner through `ps` (GitLab #40, bug report 038).

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [ -z "$TAG_CREATION_TOKEN" ]; then
    echo "Error: TAG_CREATION_TOKEN CI/CD variable is not set. See docs/self-hosting.md."
    exit 1
fi

# The tag is made with git, not with POST /repository/tags: through the API the tagger of an
# annotated tag is always the token's bot user, whose address names the private GitLab host
# (issue #207). This identity is on the public-history allowlist (scripts/ci/public_guard.py).
TAGGER_NAME="${TAGGER_NAME:-ci-release-tagging}"
TAGGER_EMAIL="${TAGGER_EMAIL:-ci-release-tagging@users.noreply.example.com}"
PUSH_URL="${TAG_PUSH_URL:-${CI_SERVER_URL}/${CI_PROJECT_PATH}.git}"

# Pushes one tag over HTTPS with the project token. The credential goes in through git's
# environment config (GIT_CONFIG_*), never `-c http.extraHeader=...`, so it is not on a command line.
push_tag() {
    local tag_name="$1"
    if [ -n "${TAG_PUSH_URL:-}" ]; then
        git push "$PUSH_URL" "refs/tags/${tag_name}"
        return
    fi
    local auth
    auth=$(printf 'oauth2:%s' "$TAG_CREATION_TOKEN" | base64 -w0)
    GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=http.extraHeader \
        GIT_CONFIG_VALUE_0="Authorization: Basic ${auth}" \
        git push "$PUSH_URL" "refs/tags/${tag_name}"
}

create_tag() {
    local tag_name="$1"
    local message="$2"

    if curl -sf --header @<(printf 'PRIVATE-TOKEN: %s\n' "$TAG_CREATION_TOKEN") \
        "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/repository/tags/${tag_name}" >/dev/null 2>&1; then
        echo "Tag $tag_name already exists, skipping."
        return 0
    fi

    echo "Creating tag $tag_name at ${CI_COMMIT_SHA}..."
    git -c "user.name=${TAGGER_NAME}" -c "user.email=${TAGGER_EMAIL}" \
        tag -a "${tag_name}" "${CI_COMMIT_SHA}" -m "${message}"
    push_tag "$tag_name"
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
