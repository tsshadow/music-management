#!/bin/bash
# Shellcheck over every tracked shell script.
#
# Gates at `warning`. The gate started at `error` because the tree carried 32
# warnings on the day it was added; those were fixed (issue #33), so the floor
# is now `warning` and there is no baseline -- a new warning fails the job.
# Where a warning is intentional, silence that one line with
# `# shellcheck disable=SCxxxx # <reason>` rather than lowering the floor.
# `info`/`style` findings are not gated.
#
# Runs shellcheck from its own image, so nothing has to be installed on the
# runner or on a developer's machine.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SEVERITY="${SHELLCHECK_SEVERITY:-warning}"
IMAGE="${SHELLCHECK_IMAGE:-koalaman/shellcheck:stable}"

mapfile -t FILES < <(
    find . -name '*.sh' \
        -not -path './.git/*' \
        -not -path '*/node_modules/*' \
        -not -path '*/build/*' \
        -not -path './.claude/*' \
        | sort
)

if [ "${#FILES[@]}" -eq 0 ]; then
    echo "--- No shell scripts found, nothing to check ---"
    exit 0
fi

echo "--- Running shellcheck (severity=$SEVERITY) over ${#FILES[@]} scripts ---"

if command -v shellcheck >/dev/null 2>&1; then
    shellcheck --severity="$SEVERITY" -f gcc "${FILES[@]}"
else
    docker run --rm -v "$ROOT_DIR:/mnt" -w /mnt "$IMAGE" \
        --severity="$SEVERITY" -f gcc "${FILES[@]}"
fi

echo "--- Shellcheck passed ---"
