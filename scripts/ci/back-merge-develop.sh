#!/bin/bash
# scripts/ci/back-merge-develop.sh
#
# Runs on `master` after release:tag, right after a release/* (or hotfix/*)
# branch has been merged. Automatically merges `master` into `develop` via
# the GitLab API so develop never drifts from what was actually released -
# see docs/release-management.md for the full policy.
#
# Uses the same TAG_CREATION_TOKEN (Maintainer, api scope) already used by
# release:tag; no new secret needed.

set -e

if [ -z "$TAG_CREATION_TOKEN" ]; then
    echo "Error: TAG_CREATION_TOKEN CI/CD variable is not set. See docs/deployment.md."
    exit 1
fi

API="${CI_API_V4_URL}/projects/${CI_PROJECT_ID}"

# Unshallow first: the runner's checkout of master is typically shallow, and
# a truncated history makes `merge-base --is-ancestor` unreliable (it can
# fail to find a common ancestor that does exist further back).
git fetch origin --unshallow >/dev/null 2>&1 || git fetch origin
git fetch origin develop >/dev/null 2>&1

if git merge-base --is-ancestor "${CI_COMMIT_SHA}" origin/develop; then
    echo "develop already contains ${CI_COMMIT_SHA}, nothing to back-merge."
    exit 0
fi

# Reuse an already-open master -> develop MR if one exists (e.g. a retried
# pipeline), instead of failing on GitLab's "already open" conflict.
EXISTING_IID=$(curl -sf --header "PRIVATE-TOKEN: ${TAG_CREATION_TOKEN}" \
    "${API}/merge_requests?source_branch=master&target_branch=develop&state=opened" \
    | python3 -c "import json,sys; mrs=json.load(sys.stdin); print(mrs[0]['iid'] if mrs else '')")

if [ -n "$EXISTING_IID" ]; then
    MR_IID="$EXISTING_IID"
    echo "Reusing existing open MR !${MR_IID}."
else
    echo "Opening master -> develop back-merge MR..."
    MR_RESPONSE=$(curl -sf --request POST --header "PRIVATE-TOKEN: ${TAG_CREATION_TOKEN}" \
        --data-urlencode "source_branch=master" \
        --data-urlencode "target_branch=develop" \
        --data-urlencode "title=Back-merge master into develop (${CI_COMMIT_SHORT_SHA})" \
        --data-urlencode "description=Automated back-merge after release:tag, so develop stays in sync with what was actually released on master. See docs/release-management.md." \
        --data-urlencode "remove_source_branch=false" \
        "${API}/merge_requests")
    MR_IID=$(echo "$MR_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['iid'])")
    echo "Opened MR !${MR_IID}."
fi

echo "Merging..."

MERGE_RESPONSE=$(curl -s --request PUT --header "PRIVATE-TOKEN: ${TAG_CREATION_TOKEN}" \
    --data-urlencode "merge_commit_message=Merge branch 'master' into 'develop'" \
    --data-urlencode "should_remove_source_branch=false" \
    "${API}/merge_requests/${MR_IID}/merge")

STATE=$(echo "$MERGE_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('state', ''))")

if [ "$STATE" != "merged" ]; then
    echo "Could not auto-merge !${MR_IID} (state: ${STATE:-unknown})."
    echo "$MERGE_RESPONSE"
    echo "Leaving the MR open for manual conflict resolution: ${CI_PROJECT_URL}/-/merge_requests/${MR_IID}"
    exit 1
fi

echo "Merged master into develop via MR !${MR_IID}."

# Delete the release/* (or hotfix/*) branch that was just merged into master,
# so merged release branches never accumulate on the remote. A forgotten,
# already-merged release branch left lying around is a real production risk:
# any later, delayed/re-run pipeline against it (e.g. queued behind other jobs
# on a busy shared runner) re-triggers release:build-images/deploy:prod from
# that branch's now-stale checkout, silently overwriting `latest` and
# redeploying old code - see docs/bug-reports/016-stale-release-branch-clobbered-latest-deploy.md
# for the incident this guards against.
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
elif [ "$SOURCE_BRANCH" = "master" ] || [ "$SOURCE_BRANCH" = "develop" ]; then
    echo "Refusing to delete protected branch '${SOURCE_BRANCH}'."
else
    echo "Deleting merged branch '${SOURCE_BRANCH}'..."
    DELETE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --request DELETE \
        --header "PRIVATE-TOKEN: ${TAG_CREATION_TOKEN}" \
        "${API}/repository/branches/$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$SOURCE_BRANCH")")
    if [ "$DELETE_STATUS" = "204" ]; then
        echo "Deleted branch '${SOURCE_BRANCH}'."
    else
        echo "Warning: could not delete branch '${SOURCE_BRANCH}' (HTTP ${DELETE_STATUS}); leaving it - delete manually."
    fi
fi
