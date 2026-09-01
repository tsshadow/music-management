#!/bin/bash
# scripts/ci/verify-prod-version.sh
#
# Refuses to tag a release that never reached production.
#
# Release 0.19.0 is why this exists. muma-mobile:check failed on the release
# branch, so release:build-images, mobile:build-release and muma:deploy
# were all reported as *skipped* - and a skipped job blocks nothing. The merge
# to master went through, release:tag and release:back-merge-develop ran
# happily from the master pipeline, and every signal in GitLab said 0.19.0 had
# shipped while production sat on 0.18.2 for a day.
#
# The post-deploy gate (scripts/ci/post-deploy-verify.sh) cannot catch that
# one: it runs inside muma:deploy, and muma:deploy is exactly the job that
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
    echo "This means the release branch's muma:deploy did not run, or did not"
    echo "succeed. A skipped job blocks nothing in GitLab, so check the release"
    echo "branch pipeline for a *skipped* muma:deploy before re-running this."
    echo
    echo "Two things follow from this job failing, for whoever picks it up:"
    echo
    echo "  1. release:tag needs this job, so no tag was created and"
    echo "     release:back-merge-develop did not run either. The merged"
    echo "     release branch IS still deleted (release:cleanup-branch does not"
    echo "     depend on this), so recover by cutting the next release from"
    echo "     develop - not by re-running the old branch's pipeline, which"
    echo "     would republish stale images as :latest (bug-report 016)."
    echo
    echo "  2. master is now ahead of develop, and both have touched"
    echo "     CHANGELOG.md. master carries a finalized '## [${EXPECTED_VERSION}]'"
    echo "     heading that develop does not, while develop may still hold"
    echo "     [Unreleased] entries master already filed under that heading."
    echo "     Reconcile those before cutting the next release, or its"
    echo "     changelog will file new entries under a version that shipped."
    exit 1
fi

echo "--- Production is serving ${version}, matching VERSION ---"
