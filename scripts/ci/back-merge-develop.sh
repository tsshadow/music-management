#!/bin/bash
# scripts/ci/back-merge-develop.sh
#
# Runs on `master` after release:tag, right after a release/* (or hotfix/*)
# branch has been merged. Merges `master` into `develop`, so develop never
# drifts from what was actually released.
#
# The merge commit is made with git under the neutral release identity, and
# pushed to develop with the project token (Maintainer, which may push to
# develop). It is not merged through the API: GitLab then writes the merge
# commit as the token's bot user, whose address names the private GitLab host,
# and public:history fails on every such commit (the same reason
# create-release-tags.sh tags with git, issue #207).
#
# Uses the same TAG_CREATION_TOKEN (Maintainer, api scope) already used by
# release:tag; no new secret needed. The credential goes in through git's
# environment config (GIT_CONFIG_*), never on a command line, because a
# command line is readable by every account on the shell-executor runner
# through `ps` (GitLab #40, bug report 038).
#
# Exits non-zero only when a person is needed: a real conflict, or a develop
# that kept moving through every retry.

set -euo pipefail

if [ -z "${TAG_CREATION_TOKEN:-}" ]; then
    echo "Error: TAG_CREATION_TOKEN CI/CD variable is not set. See docs/self-hosting.md."
    exit 1
fi

MERGE_NAME="${MERGE_NAME:-ci-release-tagging}"
MERGE_EMAIL="${MERGE_EMAIL:-ci-release-tagging@users.noreply.example.com}"
PUSH_URL="${BACKMERGE_PUSH_URL:-${CI_SERVER_URL}/${CI_PROJECT_PATH}.git}"
MESSAGE="Merge branch 'master' into 'develop'"

# Runs git with the project token as an HTTP header. A test sets BACKMERGE_PUSH_URL to a local
# repository, which needs no credential.
git_remote() {
    if [ -n "${BACKMERGE_PUSH_URL:-}" ]; then
        git "$@"
        return
    fi
    local auth
    auth=$(printf 'oauth2:%s' "$TAG_CREATION_TOKEN" | base64 -w0)
    GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=http.extraHeader \
        GIT_CONFIG_VALUE_0="Authorization: Basic ${auth}" \
        git "$@"
}

# Unshallow first: the runner's checkout of master is typically shallow, and
# a truncated history makes `merge-base --is-ancestor` unreliable.
git fetch --quiet --unshallow origin >/dev/null 2>&1 || true

for attempt in 1 2 3; do
    git_remote fetch --quiet "$PUSH_URL" "+refs/heads/develop:refs/back-merge/develop"
    if git merge-base --is-ancestor "${CI_COMMIT_SHA}" refs/back-merge/develop; then
        echo "develop already contains ${CI_COMMIT_SHA}, nothing to back-merge."
        exit 0
    fi

    git checkout --quiet --detach refs/back-merge/develop
    # GIT_COMMITTER_* and GIT_AUTHOR_* beat `-c user.*`, and the CI image sets them, so set them all.
    if ! GIT_AUTHOR_NAME="$MERGE_NAME" GIT_AUTHOR_EMAIL="$MERGE_EMAIL" \
        GIT_COMMITTER_NAME="$MERGE_NAME" GIT_COMMITTER_EMAIL="$MERGE_EMAIL" \
        git -c "user.name=${MERGE_NAME}" -c "user.email=${MERGE_EMAIL}" \
        merge --quiet --no-ff --no-edit -m "$MESSAGE" "${CI_COMMIT_SHA}"; then
        git merge --abort >/dev/null 2>&1 || true
        echo "master ${CI_COMMIT_SHA} does not merge into develop without a conflict."
        echo "A person must merge master into develop and resolve it (usually CHANGELOG.md)."
        exit 1
    fi

    if git_remote push --quiet "$PUSH_URL" "HEAD:refs/heads/develop"; then
        echo "Merged master ${CI_COMMIT_SHA} into develop as $(git rev-parse --short HEAD)."
        exit 0
    fi
    echo "  develop moved during attempt ${attempt}, trying again..."
    sleep 5
done

echo "develop kept moving; master ${CI_COMMIT_SHA} is not merged into it."
exit 1

# The release/* branch that was merged into master is deleted by its own job
# (release:cleanup-branch -> scripts/ci/delete-merged-release-branch.sh), not
# here. It used to be the tail of this script, which tied the cleanup to things
# it has nothing to do with, and left merged release branches alive on the
# remote: the precondition for bug-report 016.
