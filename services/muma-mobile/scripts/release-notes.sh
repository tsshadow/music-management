#!/bin/bash
# Print the release notes of one app version from a RELEASE_NOTES.md, without the heading and
# without blank lines at the start or the end. Prints nothing when the version has no section.
#
# Usage: release-notes.sh <version> [RELEASE_NOTES.md]
#
# scripts/release/assemble_changelog.py writes a section as `## Global Version 7.18.4 (2026-10-30)`;
# hand-written sections from before the fragments used `## [7.18.4]`. Both are read. A section ends
# at the next `## ` heading; `### ` subheadings stay in it.
set -eo pipefail

VERSION="$1"
FILE="${2:-RELEASE_NOTES.md}"
[ -n "$VERSION" ] || { echo "usage: $0 <version> [file]" >&2; exit 2; }

awk -v ver="$VERSION" '
/^## / {
    if (flag) exit
    if (index($0, "## [" ver "]") == 1 || $0 == "## Global Version " ver || index($0, "## Global Version " ver " ") == 1) flag = 1
    next
}
flag
' "$FILE" | sed '/./,$!d' | sed -e :a -e '/^\n*$/{$d;N;ba' -e '}'
