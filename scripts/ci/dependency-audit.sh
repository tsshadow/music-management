#!/bin/bash
# scripts/ci/dependency-audit.sh
# Checks dependencies against the published vulnerability databases: pip-audit
# for Python, `npm audit` for the frontend.
#
# The Python side audits the *installed* environment rather than the
# requirements files. pip-audit's requirements mode builds a throwaway virtualenv
# to resolve them, which needs ensurepip and network access and is not available
# on every runner; the installed environment is also what actually runs, so a
# finding there is never theoretical. Fix one by bumping the pin in the
# requirements file and reinstalling -- not by adding it to the accepted list
# unless it genuinely cannot be fixed yet.
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
if [ -f "$ACCEPTED_FILE" ]; then
    while read -r advisory; do
        [ -n "$advisory" ] && IGNORE_ARGS+=(--ignore-vuln "$advisory")
    done < <(sed 's/#.*//' "$ACCEPTED_FILE" | tr -d '[:blank:]' | grep -v '^$')
    echo "Accepted findings (see $ACCEPTED_FILE): ${#IGNORE_ARGS[@]} advisories" | sed 's/ [0-9]* advisories/ '"$(( ${#IGNORE_ARGS[@]} / 2 ))"' advisories/'
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
