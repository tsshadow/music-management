#!/bin/bash
# scripts/ci/delete-merged-release-branch.sh
#
# Deletes the release/* (or hotfix/*) branch that was just merged into master,
# so merged release branches never accumulate on the remote.
#
# A forgotten, already-merged release branch is a real production risk: any
# later delayed or manually re-run pipeline against it re-triggers
# release:build-images and muma:deploy from that branch's now-stale checkout,
# silently overwriting `latest` and redeploying old code. See
# docs/bug-reports/016-stale-release-branch-clobbered-latest-deploy.md.
#
# This used to be the tail of scripts/ci/back-merge-develop.sh, which made the
# cleanup conditional on things it has nothing to do with. Two ways that bit:
#
#   1. back-merge-develop.sh returns early ("develop already contains ...,
#      nothing to back-merge") *before* it reached the delete, so a release
#      whose commit was already on develop kept its branch forever. That is
#      how release/0.8.3 survived its own merge.
#   2. release:back-merge-develop needs release:tag, which now needs
#      release:verify-deployed. So the one case the deployed-version gate
#      exists to catch - production not serving what master says - was also
#      the case that left the stale branch alive, which is precisely the
#      precondition for bug 016.
#
# Deleting a branch that is already merged into master is safe no matter what
# the tag or the deploy did, so this job depends on neither. Recovering a
# release that did not deploy means cutting the next one from develop, not
# re-running the old branch's pipeline - see docs/release-management.md.
#
# Uses the same TAG_CREATION_TOKEN (Maintainer, api scope) as release:tag.

set -e

if [ -z "$TAG_CREATION_TOKEN" ]; then
    echo "Error: TAG_CREATION_TOKEN CI/CD variable is not set. See docs/deployment.md."
    exit 1
fi

API="${CI_API_V4_URL}/projects/${CI_PROJECT_ID}"

echo "Looking up the release/hotfix branch merged into master at ${CI_COMMIT_SHA}..."
SOURCE_BRANCH=$(curl -sf --header "PRIVATE-TOKEN: ${TAG_CREATION_TOKEN}" \
    "${API}/merge_requests?target_branch=master&state=merged&order_by=updated_at&sort=desc&per_page=20" \
    | python3 -c "
import json, sys
mrs = json.load(sys.stdin)
target_sha = '${CI_COMMIT_SHA}'
for mr in mrs:
    sha = mr.get('merge_commit_sha') or mr.get('sha')
    branch = mr.get('source_branch', '')
    if sha == target_sha and (branch.startswith('release/') or branch.startswith('hotfix/')):
        print(branch)
        break
")

if [ -z "$SOURCE_BRANCH" ]; then
    echo "No matching merged release/hotfix branch found for this commit, nothing to delete."
    exit 0
fi

if [ "$SOURCE_BRANCH" = "master" ] || [ "$SOURCE_BRANCH" = "develop" ]; then
    echo "Refusing to delete protected branch '${SOURCE_BRANCH}'."
    exit 0
fi

echo "Deleting merged branch '${SOURCE_BRANCH}'..."
ENCODED=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$SOURCE_BRANCH")
DELETE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --request DELETE \
    --header "PRIVATE-TOKEN: ${TAG_CREATION_TOKEN}" \
    "${API}/repository/branches/${ENCODED}")

if [ "$DELETE_STATUS" = "204" ]; then
    echo "Deleted branch '${SOURCE_BRANCH}'."
elif [ "$DELETE_STATUS" = "404" ]; then
    echo "Branch '${SOURCE_BRANCH}' is already gone."
else
    echo "Warning: could not delete branch '${SOURCE_BRANCH}' (HTTP ${DELETE_STATUS}); leaving it - delete manually."
fi
