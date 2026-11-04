#!/bin/bash
# scripts/ci/public-history-check.sh
# Fails when personal data is in the author, committer or message of a commit, or the tagger or
# message of a tag, that reaches the public repository. public-check.sh only reads tracked files.
#
# What counts is in scripts/ci/public_guard.py: the identity allowlist, the patterns from
# scripts/ci/public-patterns.txt and the banned-word digests. The output has commit ids and the kind
# of finding, never the value.
#
# Scope:
#   merge request pipeline, or a branch other than develop/master:
#       only the commits the branch adds: origin/develop..<tip>. GitLab makes the merge commit after
#       the pipeline, so its identity cannot be checked here.
#   branch pipeline of develop or master: every commit of both branches and every tag
#
# Usage: ./scripts/ci/public-history-check.sh [--full | --range A..B]   (no argument: pick by CI variables)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
GUARD="$ROOT_DIR/scripts/ci/public_guard.py"

mode="${1:-}"
if [ -z "$mode" ]; then
    branch="${CI_COMMIT_BRANCH:-}"
    if [ "$branch" = "develop" ] || [ "$branch" = "master" ]; then
        mode="--full"
    else
        tip="${CI_MERGE_REQUEST_SOURCE_BRANCH_SHA:-HEAD}"
        mode="--range origin/develop..$tip"
    fi
fi

# The CI clone is shallow and holds no tags: fetch what the chosen scope needs.
if [ -n "${CI:-}" ]; then
    git fetch --quiet --unshallow origin >/dev/null 2>&1 || true
    git fetch --quiet --tags origin >/dev/null 2>&1 || true
    git fetch --quiet origin develop master >/dev/null 2>&1 || git fetch --quiet origin develop >/dev/null 2>&1 || true
fi

case "$mode" in
    --full)
        exec python3 "$GUARD" history --full
        ;;
    --range)
        exec python3 "$GUARD" history --range "$2"
        ;;
    --range=*)
        exec python3 "$GUARD" history --range "${mode#--range=}"
        ;;
    *)
        # "--range A..B" produced above as one string.
        exec python3 "$GUARD" history --range "${mode#--range }"
        ;;
esac
