#!/bin/bash
# scripts/ci/verify-prod-version.sh
#
# Refuses to tag a release that never reached production.
#
# Release 0.19.0 is why this exists. muma-mobile:check failed on the release
# branch, so release:build-images, muma-mobile:build-release and deploy:prod
# were all reported as *skipped* - and a skipped job blocks nothing. The merge
# to master went through, release:tag and release:back-merge-develop ran
# happily from the master pipeline, and every signal in GitLab said 0.19.0 had
# shipped while production sat on 0.18.2 for a day.
#
# The post-deploy gate (scripts/ci/post-deploy-verify.sh) cannot catch that
# one: it runs inside deploy:prod, and deploy:prod is exactly the job that
# never ran. This check is the other half - it asks production what it is
# serving and compares that against the VERSION being tagged.
#
# Usage: ./scripts/ci/verify-prod-version.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# shellcheck source=scripts/ci/prod-ssh-setup.sh
. "$SCRIPT_DIR/prod-ssh-setup.sh"

EXPECTED_VERSION="$(tr -d '[:space:]' < "$PROJECT_ROOT/VERSION")"

echo "--- Asking production which version it is serving ---"
body="$(ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" \
    "curl -sS --max-time 10 http://localhost:8000/health" 2>&1 || true)"

version="$(printf '%s' "$body" | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"

if [ -z "$version" ]; then
    echo "Error: production did not report a version. Raw response:"
    printf '%s\n' "$body" | sed 's/^/  /'
    exit 1
fi

if [ "$version" != "$EXPECTED_VERSION" ]; then
    echo "Error: refusing to tag ${EXPECTED_VERSION} - production is serving ${version}."
    echo
    echo "This means the release branch's deploy:prod did not run, or did not"
    echo "succeed. A skipped job blocks nothing in GitLab, so check the release"
    echo "branch pipeline for a *skipped* deploy:prod before re-running this."
    exit 1
fi

echo "--- Production is serving ${version}, matching VERSION ---"
