#!/bin/bash
# scripts/ci/public-check.sh
# Fails when a tracked file holds personal data that must not reach the public mirror.
#
# Two checks:
#   1. gitleaks over the working tree (skipped when PUBLIC_CHECK_SKIP_GITLEAKS=1 or no docker).
#   2. git grep with scripts/ci/public-patterns.txt: names, hosts, LAN addresses.
#
# Excluded: scripts/ci/public-patterns.txt, which holds the patterns.
#
# Usage: ./scripts/ci/public-check.sh      (exit 0 clean, exit 1 on a hit)
# Env:   PUBLIC_CHECK_SKIP_GITLEAKS=1   skip the gitleaks step (used by the unit test)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
PATTERNS="${PUBLIC_CHECK_PATTERNS:-$ROOT_DIR/scripts/ci/public-patterns.txt}"
status=0

if [ "${PUBLIC_CHECK_SKIP_GITLEAKS:-0}" = "1" ]; then
    echo "--- gitleaks skipped (PUBLIC_CHECK_SKIP_GITLEAKS=1) ---"
elif command -v docker >/dev/null 2>&1; then
    # Same mechanism as security:secret-scan: gitleaks as a container on the host daemon.
    IMAGE="${GITLEAKS_IMAGE:-zricethezav/gitleaks:v8.18.4}"
    echo "--- gitleaks over the working tree (${IMAGE}) ---"
    if ! docker run --rm -v "$ROOT_DIR:/repo" -w /repo "$IMAGE" detect --no-git --source=/repo \
        --config=/repo/security/gitleaks.toml --redact; then
        status=1
    fi
elif [ -n "${CI:-}" ]; then
    echo "ERROR: docker is missing in CI, so gitleaks cannot run." >&2
    status=1
else
    echo "WARNING: docker is missing, gitleaks skipped. CI runs it." >&2
fi

echo "--- personal-data patterns ---"
# git grep -f treats every line as a pattern, so strip comments and blanks first.
CLEAN="$(mktemp)"
trap 'rm -f "$CLEAN"' EXIT
grep -v -e '^[[:space:]]*#' -e '^[[:space:]]*$' "$PATTERNS" > "$CLEAN" || true
if [ ! -s "$CLEAN" ]; then
    echo "ERROR: no patterns in $PATTERNS, so the check proves nothing." >&2
    exit 1
fi
# git grep exits 0 on a hit, 1 on no hit, anything else on an error (bad PCRE, unreadable file).
rc=0
git grep -P -i -n -I -f "$CLEAN" -- . ':!scripts/ci/public-patterns.txt' || rc=$?
case "$rc" in
    0)
        echo "ERROR: personal data in tracked files (see hits above)." >&2
        status=1
        ;;
    1)
        echo "--- clean ---"
        ;;
    *)
        echo "ERROR: git grep failed with exit code $rc, so this check proves nothing." >&2
        status=1
        ;;
esac
exit "$status"
