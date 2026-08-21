#!/bin/bash
# scripts/ci/sast.sh
# Static application security testing with semgrep's curated `p/default` rules.
#
# The tree already carries 232 findings, so a job that simply fails on any
# finding would be red on the day it is added and ignored by the day after.
# Instead every current finding is written down in
# security/accepted-sast-findings.txt, grouped by rule with a reason, and this
# script fails only on something that is *not* in that file. A new instance of
# an already-accepted rule still fails: the accepted list is per finding, not
# per rule, so "we already do this elsewhere" never silently covers a new site.
#
# A finding is identified by its rule, its file and the text of the line it sits
# on -- not its line number, which moves whenever anything above it changes.
# Editing the flagged line itself does invalidate the entry, which is intended:
# the code changed, so the acceptance should be re-read.
#
# Regenerate the file after auditing new findings:
#   SAST_WRITE_BASELINE=1 ./scripts/ci/sast.sh
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

BASELINE="security/accepted-sast-findings.txt"
CONFIG="${SAST_CONFIG:-p/default}"
IMAGE="${SAST_IMAGE:-semgrep/semgrep:latest}"
REPORT="$(mktemp)"
trap 'rm -f "$REPORT"' EXIT

echo "--- Running semgrep ($CONFIG) ---"

if command -v semgrep >/dev/null 2>&1; then
    semgrep scan --config "$CONFIG" --metrics=off --json --quiet \
        --exclude=node_modules --exclude=build > "$REPORT"
else
    docker run --rm -v "$ROOT_DIR:/src" -w /src "$IMAGE" \
        semgrep scan --config "$CONFIG" --metrics=off --json --quiet \
        --exclude=node_modules --exclude=build > "$REPORT"
fi

if [ ! -s "$REPORT" ]; then
    echo "Error: semgrep produced no report. Treating that as a failure rather"
    echo "than as a clean run -- an empty report is what a crashed scan and a"
    echo "clean tree look like alike."
    exit 1
fi

if [ "${SAST_WRITE_BASELINE:-0}" = "1" ]; then
    python3 scripts/ci/sast_baseline.py write "$REPORT" "$BASELINE"
    echo "--- Wrote $BASELINE ---"
    exit 0
fi

python3 scripts/ci/sast_baseline.py check "$REPORT" "$BASELINE"
