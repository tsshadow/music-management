#!/bin/bash
# scripts/ci/release-version-check.sh
#
# Gates the release build on a release/* or hotfix/* branch: fails the pipeline
# (before any production deploy or official MuMa Mobile upload happens) if the
# stabilization work required by the operator's release runbook wasn't actually
# done. Every check is measured against the branch this one was cut from -
# develop for a release, master for a hotfix - see BASE_BRANCH below:
#   - root VERSION must have been bumped compared to that base.
#   - CHANGELOG.md must have been touched, and must contain a dated entry for
#     the bumped VERSION (i.e. [Unreleased] was finalized into that entry -
#     [Unreleased] itself is expected to be empty again afterwards, ready for
#     the next cycle).
#   - RELEASE_NOTES.md must have been touched.
#   - if the app changed since the last release (anything under
#     services/muma-mobile/ or services/frontend/, compared to master), its
#     versionCode must differ from master's.

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

# Which branch this release is measured against. A release/* branch is cut from
# develop, so develop is the "before" picture. A hotfix/* branch is cut from
# master and deliberately does *not* contain what is queued on develop, so
# comparing it to develop reports develop's unreleased work as changes made by
# the hotfix. Overridable for testing.
case "${CI_COMMIT_BRANCH:-}" in
    hotfix/*) BASE_BRANCH="master" ;;
    *)        BASE_BRANCH="develop" ;;
esac
BASE="${VERSION_CHECK_BASE:-origin/${BASE_BRANCH}}"

# Full fetch, not --depth: a release branch further than the depth from its base
# silently compares against a truncated history.
git fetch origin "$BASE_BRANCH" >/dev/null 2>&1 || git fetch origin "$BASE_BRANCH"

echo "Comparing against ${BASE}."

fail() {
    echo "release:version-check FAILED: $1"
    exit 1
}

# 1. VERSION must be bumped.
if git diff --quiet "$BASE" -- VERSION; then
    fail "VERSION was not bumped on this release branch (still matches develop)."
fi
echo "OK: VERSION bumped to $(cat VERSION)."

# 2. CHANGELOG.md must be touched, and contain a dated entry for VERSION
# (this is how we know [Unreleased] was actually finalized into a release,
# rather than just edited some other way).
if git diff --quiet "$BASE" -- CHANGELOG.md; then
    fail "CHANGELOG.md was not updated on this release branch."
fi
RELEASE_VERSION=$(cat VERSION)
if ! grep -q "^## \[${RELEASE_VERSION}\]" CHANGELOG.md; then
    fail "CHANGELOG.md has no dated entry for [${RELEASE_VERSION}] (VERSION was bumped, but [Unreleased] wasn't finalized into a matching entry)."
fi
echo "OK: CHANGELOG.md has a dated [${RELEASE_VERSION}] entry."

# 2b. A release that adds something is a feature release: minor bump, patch
# reset. Everything else is a patch bump. Without this the version number is
# just a build counter - which is what 47 consecutive 0.0.x releases were.
BASE_VERSION=$(git show "${BASE}:VERSION" | tr -d '[:space:]')
IFS='.' read -r BASE_MAJOR BASE_MINOR _ <<< "$BASE_VERSION"
IFS='.' read -r NEW_MAJOR NEW_MINOR NEW_PATCH <<< "$RELEASE_VERSION"

# The section body for this release: everything between its heading and the
# next `## [` heading. A previous release's ### Added must not count.
RELEASE_SECTION=$(awk -v version="$RELEASE_VERSION" '
    $0 ~ "^## \\[" version "\\]" { inside = 1; next }
    inside && /^## \[/ { exit }
    inside { print }
' CHANGELOG.md)

if grep -q '^### Added' <<< "$RELEASE_SECTION"; then
    if [ "$NEW_MAJOR" = "$BASE_MAJOR" ] && [ "$NEW_MINOR" -le "$BASE_MINOR" ]; then
        fail "CHANGELOG [${RELEASE_VERSION}] has an '### Added' section, so this is a feature release and must bump the minor version (from ${BASE_VERSION}, expected ${BASE_MAJOR}.$((BASE_MINOR + 1)).0), not the patch version."
    fi
    if [ "$NEW_PATCH" != "0" ]; then
        fail "A minor bump resets the patch version to 0, so ${RELEASE_VERSION} should be ${NEW_MAJOR}.${NEW_MINOR}.0."
    fi
    echo "OK: feature release, minor version bumped to ${RELEASE_VERSION}."
else
    echo "OK: no '### Added' section, a patch bump to ${RELEASE_VERSION} is fine."
fi

# 3. RELEASE_NOTES.md must be touched.
if git diff --quiet "$BASE" -- RELEASE_NOTES.md; then
    fail "RELEASE_NOTES.md was not updated on this release branch."
fi
echo "OK: RELEASE_NOTES.md updated."

# 4. If the app changed since the last release, its versionCode must move too.
#
# Measured against master (the last release), not against develop: a release
# branch is cut from develop, so everything merged there before the cut is
# invisible in a diff against develop -- which is how 0.84.0 shipped a new web
# UI while the APK kept versionCode 352 and no phone was offered the update.
# services/frontend/ counts because the Capacitor shell serves the web bundle
# baked into the APK (build.gradle's prepareWebBundle), not one from the server.
SHIPPED="${APP_CHECK_BASE:-origin/master}"
if [ "$BASE_BRANCH" != "master" ]; then
    git fetch origin master >/dev/null 2>&1 || git fetch origin master
fi
version_code() {
    grep -oE 'versionCode[[:space:]]+[0-9]+' | head -1 | grep -oE '[0-9]+$'
}
if ! git diff --quiet "$SHIPPED" -- services/muma-mobile/ services/frontend/ 2>/dev/null; then
    SHIPPED_CODE=$(git show "${SHIPPED}:services/muma-mobile/app/build.gradle" 2>/dev/null | version_code || true)
    CURRENT_CODE=$(version_code < services/muma-mobile/app/build.gradle || true)
    if [ -n "$SHIPPED_CODE" ] && [ "$SHIPPED_CODE" = "$CURRENT_CODE" ]; then
        fail "the app (services/muma-mobile or services/frontend) changed since ${SHIPPED}, but versionCode is still ${CURRENT_CODE}: bump versionCode/versionName in services/muma-mobile/app/build.gradle, or no phone is offered the new build."
    fi
    echo "OK: the app changed since ${SHIPPED} and versionCode moved (${SHIPPED_CODE:-none} -> ${CURRENT_CODE})."
fi

echo "release:version-check passed."
