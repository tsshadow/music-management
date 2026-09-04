#!/bin/bash
# Fails a merge request that adds no changelog fragment.
#
# The fragments only work if they are actually written. Nobody forgets the
# entry for a change they are proud of; the ones that go missing are the
# behaviour changes someone else has to discover in production later. So the
# pipeline asks, rather than the reviewer.
#
# The escape is a `no-changelog` label on the merge request, for the changes
# that genuinely have no reader-facing line: a typo, a baseline bump, a test.
# It is a label rather than a magic commit-message line so that it stays
# visible on the merge request itself.
#
# Usage: ./scripts/ci/changelog-fragment-check.sh
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

LABELS="${CI_MERGE_REQUEST_LABELS:-}"
TARGET="${CI_MERGE_REQUEST_TARGET_BRANCH_NAME:-}"
SOURCE="${CI_MERGE_REQUEST_SOURCE_BRANCH_NAME:-}"

if [[ ",$LABELS," == *",no-changelog,"* ]]; then
    echo "--- no-changelog label set, skipping ---"
    exit 0
fi

# A release branch is the one place that *removes* fragments, and its own
# CHANGELOG.md edit is the assembled result. Asking it for a fragment would
# make every release red.
if [[ "$SOURCE" =~ ^(release|hotfix)/ ]]; then
    echo "--- release branch, skipping ---"
    exit 0
fi

if [ -z "$TARGET" ]; then
    echo "--- not a merge request pipeline, skipping ---"
    exit 0
fi

# The clone is shallow (GIT_DEPTH), so the target branch and the merge base are
# usually not in it. Fetch just enough of the target to diff against.
git fetch --quiet --depth=50 origin "$TARGET" 2>/dev/null || git fetch --quiet origin "$TARGET"

BASE="$(git merge-base FETCH_HEAD HEAD 2>/dev/null)"
if [ -z "$BASE" ]; then
    echo "Could not find a merge base with $TARGET. Treating that as a pass rather"
    echo "than failing a merge request over the shape of the clone."
    exit 0
fi

ADDED="$(git diff --name-only --diff-filter=A "$BASE" HEAD -- 'changelog.d/*.md' 'changelog.d/**/*.md' \
    | grep -v '^changelog.d/README.md$')"

if [ -n "$ADDED" ]; then
    echo "--- changelog fragment(s) added ---"
    echo "$ADDED"
    exit 0
fi

cat <<'MSG'
No changelog fragment in this merge request.

Add a file under changelog.d/ named <slug>.<section>.md -- the merge request
number makes an obvious slug, and the section is one of added, changed,
deprecated, removed, fixed, security:

    changelog.d/619.fixed.md

changelog.d/README.md has the format, including the shorter RELEASE_NOTES.md
wording. If this change genuinely needs no line, label the merge request
`no-changelog`.
MSG
exit 1
