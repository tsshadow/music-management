#!/bin/bash
# scripts/test/muma-server-format.sh
# C++ formatting for the MuMa Server, against the .clang-format that has been
# sitting in services/music-management-server/ being read by nothing.
#
# Of the four components this was the last one with no formatting gate at all,
# and the only one with no static analysis of any kind. The whole tree turned
# out to be 37 files out of 870 -- `ColumnLimit: 0` in the config means
# clang-format never reflows a line, so it only ever fixes bracing, spacing and
# indentation.
#
# The version is pinned, and the image is one that ships clang-format rather
# than installing it. Both matter:
#
#   - clang-format changes its output between releases. alpine 3.21 ships
#     19.1.4, 3.22 ships 20.1.8, :latest was 22.1.3 when this was written, and
#     they disagree. An unpinned check goes red whenever the base image moves
#     and blames whoever pushed next.
#   - installing a package needs root, and a container running as root writing
#     into a bind mount leaves root-owned files behind. That is the failure the
#     Android CI image was built to end (see docker/Dockerfile-android-ci and
#     the reclaim hook in .gitlab-ci.yml); no need to reintroduce it here.
#
# The version is printed on every run, so a silently moved tag is visible in the
# job log rather than as a mystery diff.
#
# Usage: ./scripts/test/muma-server-format.sh          # check, non-zero if dirty
#        ./scripts/test/muma-server-format.sh --fix    # rewrite in place
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVER_DIR="$ROOT_DIR/services/music-management-server"
IMAGE="silkeh/clang:20"

MODE=check
[ "${1:-}" = "--fix" ] && MODE=fix

echo "--- Running clang-format ($MODE) over the MuMa Server sources ---"

docker run --rm \
    -u "$(id -u):$(id -g)" \
    -v "$SERVER_DIR:/src" \
    -w /src \
    -e MODE="$MODE" \
    "$IMAGE" \
    sh -c '
set -e
clang-format --version

find src -name "*.cpp" -o -name "*.hpp" -o -name "*.h" > /tmp/files.txt
count=$(wc -l < /tmp/files.txt)

if [ "$MODE" = fix ]; then
    xargs clang-format -i < /tmp/files.txt
    echo "Formatted $count files."
    exit 0
fi

# Not `--dry-run --Werror`: it reports one warning per deviation, which reads
# as hundreds of problems when it is a few dozen files. Compare per file so the
# output is the list someone has to act on.
offenders=0
while read -r f; do
    if ! clang-format "$f" | diff -q "$f" - >/dev/null 2>&1; then
        echo "  needs formatting: $f"
        offenders=$((offenders + 1))
    fi
done < /tmp/files.txt

if [ "$offenders" -gt 0 ]; then
    echo ""
    echo "ERROR: $offenders of $count files are not formatted."
    echo "Fix with: ./scripts/test/muma-server-format.sh --fix"
    exit 1
fi
echo "All $count files are formatted."
'

echo "--- MuMa Server formatting OK ---"
