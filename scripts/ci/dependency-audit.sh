#!/bin/bash
# scripts/ci/dependency-audit.sh
# Checks dependencies against the published vulnerability databases: pip-audit
# for Python, `npm audit` for the frontend.
#
# The Python side audits the *installed* environment. pip-audit's requirements
# mode resolves each file in a throwaway virtualenv, which means building every
# pin from source when no wheel matches -- numpy on a slim image is enough to
# make that fail for reasons that have nothing to do with security. The
# installed environment is also what actually runs, so a finding there is never
# theoretical. Fix one by bumping the pin in the requirements file and
# reinstalling.
#
# This is why the CI job is reporting rather than gating: the result reflects
# the environment it runs in, which this repository does not manage.
#
# Consciously accepted findings live in security/accepted-vulnerabilities.txt,
# one advisory ID per line with a reason. Everything else fails this job.
#
# Exit codes:
#   0  clean (or only accepted findings)
#   1  vulnerabilities found
#   2  a scanner could not run
#
# Usage: ./scripts/ci/dependency-audit.sh [--strict]
#   --strict  also fail on moderate npm findings (default: high and above)

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

ACCEPTED_FILE="security/accepted-vulnerabilities.txt"
NPM_LEVEL=high
if [ "${1:-}" = "--strict" ]; then
    NPM_LEVEL=moderate
fi

STATUS=0
SKIPPED=0

# Advisory IDs from the accepted list, as repeated --ignore-vuln arguments.
IGNORE_ARGS=()
ACCEPTED_COUNT=0
if [ -f "$ACCEPTED_FILE" ]; then
    while read -r advisory; do
        [ -n "$advisory" ] || continue
        IGNORE_ARGS+=(--ignore-vuln "$advisory")
        ACCEPTED_COUNT=$((ACCEPTED_COUNT + 1))
    done < <(sed 's/#.*//' "$ACCEPTED_FILE" | tr -d '[:blank:]' | grep -v '^$')
    echo "Accepted findings (see $ACCEPTED_FILE): $ACCEPTED_COUNT advisories"
fi

echo
echo "=== Python dependencies (pip-audit, installed environment) ==="
if command -v pip-audit >/dev/null 2>&1; then
    if ! pip-audit --progress-spinner off "${IGNORE_ARGS[@]+"${IGNORE_ARGS[@]}"}"; then
        STATUS=1
    fi
else
    echo "pip-audit not installed (pip install -r requirements-dev.txt), skipping"
    SKIPPED=1
fi

echo
echo "=== Frontend dependencies (npm audit, level: $NPM_LEVEL) ==="
if command -v npm >/dev/null 2>&1 && [ -f services/frontend/package-lock.json ]; then
    if ! (cd services/frontend && npm audit --audit-level="$NPM_LEVEL"); then
        STATUS=1
    fi
else
    echo "npm or services/frontend/package-lock.json missing, skipping"
    SKIPPED=1
fi

if [ "$STATUS" -ne 0 ]; then
    echo
    echo "Vulnerable dependencies found."
    echo "Fix: bump the pin in the requirements file / package.json the finding names."
    echo "Only if that is genuinely not possible yet, add the advisory ID to"
    echo "$ACCEPTED_FILE with a reason and a way out."
    exit 1
fi

if [ "$SKIPPED" -ne 0 ]; then
    echo
    echo "One or more scanners could not run."
    exit 2
fi

echo
echo "No unaccepted vulnerabilities at or above the configured level."
