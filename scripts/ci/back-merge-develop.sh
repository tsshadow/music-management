#!/bin/bash
# scripts/ci/back-merge-develop.sh
#
# Runs on `master` after release:tag, right after a release/* (or hotfix/*)
# branch has been merged. Automatically merges `master` into `develop` via
# the GitLab API so develop never drifts from what was actually released -
# see the operator's release runbook for the full policy.
#
# Uses the same TAG_CREATION_TOKEN (Maintainer, api scope) already used by
# release:tag; no new secret needed.
# The token goes to curl through a process substitution (`--header @<(...)`), never as
# `--header "PRIVATE-TOKEN: $TOKEN"`: a command line is readable by every account on the
# shell-executor runner through `ps` (GitLab #40, bug report 038).

set -e

if [ -z "$TAG_CREATION_TOKEN" ]; then
    echo "Error: TAG_CREATION_TOKEN CI/CD variable is not set. See docs/self-hosting.md."
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
EXISTING_IID=$(curl -sf --header @<(printf 'PRIVATE-TOKEN: %s\n' "$TAG_CREATION_TOKEN") \
    "${API}/merge_requests?source_branch=master&target_branch=develop&state=opened" \
    | python3 -c "import json,sys; mrs=json.load(sys.stdin); print(mrs[0]['iid'] if mrs else '')")

if [ -n "$EXISTING_IID" ]; then
    MR_IID="$EXISTING_IID"
    echo "Reusing existing open MR !${MR_IID}."
else
    echo "Opening master -> develop back-merge MR..."
    MR_RESPONSE=$(curl -sf --request POST --header @<(printf 'PRIVATE-TOKEN: %s\n' "$TAG_CREATION_TOKEN") \
        --data-urlencode "source_branch=master" \
        --data-urlencode "target_branch=develop" \
        --data-urlencode "title=Back-merge master into develop (${CI_COMMIT_SHORT_SHA})" \
        --data-urlencode "description=Automated back-merge after release:tag, so develop stays in sync with what was actually released on master. See the operator's release runbook." \
        --data-urlencode "remove_source_branch=false" \
        "${API}/merge_requests")
    MR_IID=$(echo "$MR_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin)['iid'])")
    echo "Opened MR !${MR_IID}."
fi

echo "Waiting for GitLab to finish computing mergeability of !${MR_IID}..."

# GitLab computes merge_status asynchronously right after an MR is opened
# (or a source branch changes); a merge attempted immediately can fail with
# "Branch cannot be merged" purely because that computation hasn't finished
# yet, not because of a real conflict. Poll briefly before giving up.
#
# Only the states below mean "GitLab has not finished thinking"; they clear in
# seconds. Every other value is an answer, and polling past an answer burns the
# budget the transient states actually need.
is_transient_merge_status() {
    case "$1" in
        preparing | checking | unchecked | "") return 0 ;;
        *) return 1 ;;
    esac
}

MERGE_STATUS=""
for _ in 1 2 3 4 5 6 7 8 9 10; do
    MERGE_STATUS=$(curl -sf --header @<(printf 'PRIVATE-TOKEN: %s\n' "$TAG_CREATION_TOKEN") \
        "${API}/merge_requests/${MR_IID}" \
        | python3 -c "import json,sys; print(json.load(sys.stdin).get('detailed_merge_status', ''))")
    if ! is_transient_merge_status "$MERGE_STATUS"; then
        break
    fi
    echo "  merge status: ${MERGE_STATUS:-unknown}, retrying in 3s..."
    sleep 3
done

# The MR was opened seconds ago and runs its own pipeline, which the project
# requires to pass before a merge is allowed. Waiting that out here would hold a
# runner for the length of a full pipeline, and the 30 second budget above never
# came close: it timed out, merged anyway, and got back a bare
# `405 Method Not Allowed` that reads like a conflict and is not one. Hand it to
# GitLab instead -- it merges the moment the pipeline goes green, with nothing
# holding a runner in the meantime.
if [ "$MERGE_STATUS" = "ci_still_running" ] || [ "$MERGE_STATUS" = "ci_must_pass" ]; then
    echo "!${MR_IID} is waiting on its own pipeline; enabling auto-merge."
    AUTO_RESPONSE=$(curl -s --request PUT --header @<(printf 'PRIVATE-TOKEN: %s\n' "$TAG_CREATION_TOKEN") \
        --data-urlencode "merge_commit_message=Merge branch 'master' into 'develop'" \
        --data-urlencode "should_remove_source_branch=false" \
        --data-urlencode "merge_when_pipeline_succeeds=true" \
        "${API}/merge_requests/${MR_IID}/merge")
    AUTO_ENABLED=$(echo "$AUTO_RESPONSE" \
        | python3 -c "import json,sys; print('yes' if json.load(sys.stdin).get('merge_when_pipeline_succeeds') else 'no')" 2>/dev/null \
        || echo "no")
    if [ "$AUTO_ENABLED" = "yes" ]; then
        echo "Auto-merge is on for !${MR_IID}; GitLab merges it when the pipeline passes."
        echo "${CI_PROJECT_URL}/-/merge_requests/${MR_IID}"
        exit 0
    fi
    echo "Could not enable auto-merge on !${MR_IID}."
    echo "$AUTO_RESPONSE"
    echo "Leaving the MR open: ${CI_PROJECT_URL}/-/merge_requests/${MR_IID}"
    exit 1
fi

# Neither mergeable nor waiting on CI means a person is needed: a real conflict,
# a blocked MR, an unresolved discussion. Name the state, rather than attempting
# a merge that will be refused and then reporting the refusal.
if [ "$MERGE_STATUS" != "mergeable" ]; then
    echo "!${MR_IID} cannot be merged automatically (merge status: ${MERGE_STATUS:-unknown})."
    echo "Leaving the MR open for manual resolution: ${CI_PROJECT_URL}/-/merge_requests/${MR_IID}"
    exit 1
fi

echo "Merging..."

MERGE_RESPONSE=""
STATE=""
for _ in 1 2 3; do
    MERGE_RESPONSE=$(curl -s --request PUT --header @<(printf 'PRIVATE-TOKEN: %s\n' "$TAG_CREATION_TOKEN") \
        --data-urlencode "merge_commit_message=Merge branch 'master' into 'develop'" \
        --data-urlencode "should_remove_source_branch=false" \
        "${API}/merge_requests/${MR_IID}/merge")
    STATE=$(echo "$MERGE_RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('state', ''))")
    if [ "$STATE" = "merged" ]; then
        break
    fi
    echo "  merge attempt failed (state: ${STATE:-unknown}), retrying in 3s..."
    sleep 3
done

if [ "$STATE" != "merged" ]; then
    echo "Could not auto-merge !${MR_IID} (state: ${STATE:-unknown})."
    echo "$MERGE_RESPONSE"
    echo "Leaving the MR open for manual conflict resolution: ${CI_PROJECT_URL}/-/merge_requests/${MR_IID}"
    exit 1
fi

echo "Merged master into develop via MR !${MR_IID}."

# The release/* branch that was merged into master is deleted by its own job
# (release:cleanup-branch -> scripts/ci/delete-merged-release-branch.sh), not
# here. It used to be the tail of this script, which tied the cleanup to two
# things it has nothing to do with: the early return above, and - through
# release:tag's needs - the deployed-version check. Both left merged release
# branches alive on the remote, which is the precondition for bug-report 016.
