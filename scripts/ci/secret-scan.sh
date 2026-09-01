#!/bin/bash
# scripts/ci/secret-scan.sh
# Scans the repository's git history for committed credentials with gitleaks.
#
# GitLab's own Secret-Detection template is not usable here: it declares a job
# with an `image:`, and this project's runner is a shell executor. gitleaks is
# therefore invoked the same way every other tool in this repo is - through
# `docker run` against the host daemon.
#
# Scope is deliberately the git history (`gitleaks detect`), not the working
# tree. A credential only becomes a problem once it is committed, and the
# untracked files in a working tree are exactly the ones that legitimately hold
# secrets - the gitignored .env, and the file-type CI/CD variables the runner
# materialises next to the checkout. Scanning those would fail every local run
# for something that was never at risk of being published.
#
# Findings that are genuinely not secrets belong in security/gitleaks.toml with
# a comment saying why. Never silence a finding by deleting the rule.
#
# Usage: ./scripts/ci/secret-scan.sh

set -e
set -o pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

IMAGE="${GITLEAKS_IMAGE:-zricethezav/gitleaks:v8.18.4}"

# In a git worktree, .git is a *file* holding an absolute path into the main
# repository's .git directory. Mounting only the checkout leaves gitleaks with
# no history to read - and it reports "no leaks found" anyway, which is the
# worst possible answer. Mount the common git directory at the same absolute
# path so that pointer still resolves inside the container. CI checks out an
# ordinary clone, so this is a no-op there.
GIT_MOUNT=()
if [ -f "$ROOT_DIR/.git" ]; then
    GIT_COMMON_DIR="$(git rev-parse --path-format=absolute --git-common-dir)"
    GIT_MOUNT=(-v "${GIT_COMMON_DIR}:${GIT_COMMON_DIR}:ro")
    echo "--- Worktree detected; also mounting ${GIT_COMMON_DIR} ---"
fi

SCAN_LOG="$(mktemp)"
trap 'rm -f "$SCAN_LOG"' EXIT

# On a merge request, scan only the commits the merge request adds.
#
# Git history is immutable: a commit that was clean when it landed is still
# clean, so re-scanning it on every unrelated merge request buys nothing and
# costs the whole job. That was tolerable until 2026-09-01, when four
# whole-tree reformats (~700 files) landed inside the runner's 20-commit
# shallow clone and every scan went from ~9 minutes to over 20 -- past the
# job's wall, failing merge requests and a release branch for a reason that
# had nothing to do with either.
#
# The full history is still scanned where that means something: on develop, on
# master, on release branches and on the schedule, none of which set this
# variable. So a secret reaches at most one merge request before a full scan
# sees it.
#
# Verified to still catch: committing an AWS key into the scanned range fails
# the scan with `leaks found: 1` and RuleID aws-access-token.
SCOPE=(--source=/repo)
if [ -n "${CI_MERGE_REQUEST_DIFF_BASE_SHA:-}" ]; then
    echo "--- Merge request: scanning ${CI_MERGE_REQUEST_DIFF_BASE_SHA}..HEAD only ---"
    SCOPE+=(--log-opts="${CI_MERGE_REQUEST_DIFF_BASE_SHA}..HEAD")
fi

echo "--- Scanning the git history for committed secrets (${IMAGE}) ---"
docker run --rm \
    -v "$ROOT_DIR:/repo" \
    "${GIT_MOUNT[@]}" \
    -w /repo \
    "$IMAGE" detect \
    "${SCOPE[@]}" \
    --config=/repo/security/gitleaks.toml \
    --redact \
    --verbose 2>&1 | tee "$SCAN_LOG"

# gitleaks exits 0 when it cannot read the history at all - it logs the git
# failure at ERR level and then truthfully reports that it found nothing in the
# zero commits it managed to scan. Treat any error line as a failed scan: a
# scanner that cannot see the repository must not be able to pass.
if grep -q 'ERR' "$SCAN_LOG"; then
    echo "ERROR: gitleaks logged an error, so this scan proves nothing." >&2
    echo "Fix the error above and re-run; do not treat it as a clean result." >&2
    exit 1
fi

echo "--- No secrets found ---"
