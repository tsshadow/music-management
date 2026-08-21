#!/bin/bash
# Shellcheck over every tracked shell script.
#
# Gates at `error` only. The tree currently carries 32 findings at `warning`
# severity -- mostly SC2163, SC2034 and SC2164 -- and a gate that is red on the
# day it is added teaches everyone to ignore it. Lowering the floor to `warning`
# is a follow-up that fixes those 32 first; until then this catches the class of
# problem that actually breaks a script.
#
# Runs shellcheck from its own image, so nothing has to be installed on the
# runner or on a developer's machine.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SEVERITY="${SHELLCHECK_SEVERITY:-error}"
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
