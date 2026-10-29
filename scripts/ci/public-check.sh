#!/bin/bash
# scripts/ci/public-check.sh
# Fails when a tracked file holds personal data that must not reach the public mirror.
#
# Two checks:
#   1. gitleaks over the working tree (skipped when PUBLIC_CHECK_SKIP_GITLEAKS=1 or no docker).
#   2. git grep with scripts/ci/public-patterns.txt: names, hosts, LAN addresses.
#
# Excluded: scripts/ci/public-patterns.txt and docs/designs/public-edition/ (they name the
# patterns on purpose), and migrate_*.sql. A deploy re-runs a migration whose sha256 changed, so these
# files are never edited, even to remove a name.
#
# Usage: ./scripts/ci/public-check.sh      (exit 0 clean, exit 1 on a hit)
# Env:   PUBLIC_CHECK_SKIP_GITLEAKS=1   skip the gitleaks step (used by the unit test)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
PATTERNS="${PUBLIC_CHECK_PATTERNS:-$ROOT_DIR/scripts/ci/public-patterns.txt}"
status=0

if [ "${PUBLIC_CHECK_SKIP_GITLEAKS:-0}" != "1" ] && command -v docker >/dev/null 2>&1; then
    IMAGE="${GITLEAKS_IMAGE:-zricethezav/gitleaks:v8.18.4}"
    echo "--- gitleaks over the working tree (${IMAGE}) ---"
    if ! docker run --rm -v "$ROOT_DIR:/repo" -w /repo "$IMAGE" detect --no-git --source=/repo \
        --config=/repo/security/gitleaks.toml --redact; then
        status=1
    fi
else
    echo "--- gitleaks skipped ---"
fi

echo "--- personal-data patterns ---"
# git grep -f treats every line as a pattern, so strip comments and blanks first.
CLEAN="$(mktemp)"
trap 'rm -f "$CLEAN"' EXIT
grep -v -e '^[[:space:]]*#' -e '^[[:space:]]*$' "$PATTERNS" > "$CLEAN"
if git grep -P -i -n -I -f "$CLEAN" -- . ':!migrate_*.sql' ':!**/migrate_*.sql' ':!scripts/ci/public-patterns.txt' ':!docs/designs/public-edition/'; then
    echo "ERROR: personal data in tracked files (see hits above)." >&2
    status=1
else
    echo "--- clean ---"
fi
exit "$status"
