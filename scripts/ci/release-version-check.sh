#!/bin/bash
# scripts/ci/release-version-check.sh
#
# Gates deploy:prod on a release/* branch: fails the pipeline (before any
# production deploy or official Ultrasonic upload happens) if the stabilization
# work required by docs/release-management.md wasn't actually done:
#   - root VERSION must have been bumped compared to develop.
#   - CHANGELOG.md must have been touched, and its [Unreleased] section must no
#     longer be empty (i.e. it was finalized into a dated entry).
#   - RELEASE_NOTES.md must have been touched.
#   - if anything under services/ultrasonic/ changed, build.gradle's
#     versionCode/versionName must also have been bumped.

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

git fetch origin develop --depth=50 >/dev/null 2>&1 || git fetch origin develop
BASE="origin/develop"

fail() {
    echo "release:version-check FAILED: $1"
    exit 1
}

# 1. VERSION must be bumped.
if git diff --quiet "$BASE" -- VERSION; then
    fail "VERSION was not bumped on this release branch (still matches develop)."
fi
echo "OK: VERSION bumped to $(cat VERSION)."

# 2. CHANGELOG.md must be touched, and [Unreleased] must not still be empty.
if git diff --quiet "$BASE" -- CHANGELOG.md; then
    fail "CHANGELOG.md was not updated on this release branch."
fi
if grep -q "^## \[Unreleased\]" CHANGELOG.md; then
    UNRELEASED_BODY=$(awk '/^## \[Unreleased\]/{flag=1; next} /^## \[/{flag=0} flag' CHANGELOG.md | sed '/^\s*$/d')
    if [ -z "$UNRELEASED_BODY" ]; then
        fail "CHANGELOG.md's [Unreleased] section is still empty."
    fi
fi
echo "OK: CHANGELOG.md updated."

# 3. RELEASE_NOTES.md must be touched.
if git diff --quiet "$BASE" -- RELEASE_NOTES.md; then
    fail "RELEASE_NOTES.md was not updated on this release branch."
fi
echo "OK: RELEASE_NOTES.md updated."

# 4. If Ultrasonic changed, its own version must have been bumped too.
if ! git diff --quiet "$BASE" -- services/ultrasonic/ 2>/dev/null; then
    if git diff --quiet "$BASE" -- services/ultrasonic/ultrasonic/build.gradle 2>/dev/null; then
        fail "services/ultrasonic changed on this branch, but versionCode/versionName in build.gradle wasn't bumped."
    fi
    echo "OK: Ultrasonic changed and its versionCode/versionName was bumped."
fi

echo "release:version-check passed."
