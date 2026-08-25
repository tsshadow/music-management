#!/bin/bash
# scripts/ci/renovate.sh
# Runs Renovate against this GitLab instance to open dependency merge requests.
#
# The upstream renovate-runner CI template is not usable here for the same
# reason GitLab's Secret-Detection template is not: it declares a job with an
# `image:`, and this project's runner is a shell executor, so such a job never
# starts. Renovate is therefore invoked the way every other tool in this repo
# is - through `docker run` against the host daemon.
#
# Nothing from the working tree is mounted. Renovate clones the repository
# itself over the API, reads renovate.json from the branches named in
# `baseBranches`, and writes its results back as merge requests. Mounting the
# checkout would give it a second, stale copy to be confused by.
#
# Usage: RENOVATE_TOKEN=glpat-... ./scripts/ci/renovate.sh
#        DRY_RUN=full ./scripts/ci/renovate.sh   # look, change nothing

set -e
set -o pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

IMAGE="${RENOVATE_IMAGE:-renovate/renovate:41}"

if [ -z "${RENOVATE_TOKEN:-}" ]; then
    echo "ERROR: RENOVATE_TOKEN is not set." >&2
    echo "  A GitLab personal access token with the api, read_user and" >&2
    echo "  write_repository scopes. Its user authors every dependency merge" >&2
    echo "  request and needs to be able to merge one, or automerge does" >&2
    echo "  nothing." >&2
    exit 1
fi

# $CI_API_V4_URL is set by GitLab; the fallback is for running this by hand.
ENDPOINT="${RENOVATE_ENDPOINT:-${CI_API_V4_URL:-https://gitlab.example.com/api/v4}}"
REPOSITORY="${RENOVATE_REPOSITORIES:-${CI_PROJECT_PATH:-muma/music-management}}"

# Renovate reads release notes for the dependencies it proposes from github.com
# and is rate-limited to 60 requests an hour without a token. Optional: without
# it the merge requests still appear, with thinner descriptions.
GITHUB_ENV=()
if [ -n "${RENOVATE_GITHUB_COM_TOKEN:-}" ]; then
    GITHUB_ENV=(-e "GITHUB_COM_TOKEN=${RENOVATE_GITHUB_COM_TOKEN}")
fi

DRY_RUN_ENV=()
if [ -n "${DRY_RUN:-}" ]; then
    DRY_RUN_ENV=(-e "RENOVATE_DRY_RUN=${DRY_RUN}")
    echo "--- Dry run (${DRY_RUN}): nothing will be written ---"
fi

RUN_LOG="$(mktemp)"
trap 'rm -f "$RUN_LOG"' EXIT

echo "--- Running Renovate (${IMAGE}) against ${REPOSITORY} ---"
docker run --rm \
    -e "RENOVATE_TOKEN=${RENOVATE_TOKEN}" \
    -e "RENOVATE_ENDPOINT=${ENDPOINT}" \
    -e RENOVATE_PLATFORM=gitlab \
    -e RENOVATE_AUTODISCOVER=false \
    -e "RENOVATE_REPOSITORIES=${REPOSITORY}" \
    -e "LOG_LEVEL=${LOG_LEVEL:-info}" \
    "${GITHUB_ENV[@]}" \
    "${DRY_RUN_ENV[@]}" \
    "$IMAGE" 2>&1 | tee "$RUN_LOG"

# Renovate exits 0 after logging a per-repository failure: the run as a whole
# "succeeded", it just did nothing for the one repository it was given. With a
# single repository configured that is indistinguishable from success, and a
# green weekly job that silently stopped proposing updates is precisely the
# failure this whole job exists to prevent. Same reasoning as the ERR check in
# secret-scan.sh.
if grep -qE '^ *(FATAL|ERROR):' "$RUN_LOG"; then
    echo "ERROR: Renovate logged a fatal error, so this run proves nothing." >&2
    echo "Fix the error above and re-run; do not treat it as a clean result." >&2
    exit 1
fi

echo "--- Renovate finished ---"
