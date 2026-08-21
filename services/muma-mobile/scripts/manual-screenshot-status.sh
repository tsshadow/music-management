#!/bin/bash
# scripts/manual-screenshot-status.sh
#
# Says which pictures in the in-app manual are still placeholders.
#
# Every generated placeholder carries a marker in a PNG text chunk; a real screenshot does not.
# So the answer is a grep, and it stays right without anyone maintaining a list by hand: drop a
# real capture over a placeholder and it disappears from this report by itself.

set -e

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR="$HERE/../app/src/main/res/drawable-nodpi"
MARKER="muma-manual-placeholder"
DOC="services/muma-mobile/docs/manual-screenshots.md"

if [ ! -d "$DIR" ]; then
    echo "No drawable-nodpi directory at $DIR"
    exit 1
fi

missing=0
have=0

echo "Still a placeholder, a real screenshot wanted:"
for file in "$DIR"/manual_*.png; do
    [ -e "$file" ] || continue
    if grep -q "$MARKER" "$file" 2>/dev/null; then
        echo "  $(basename "$file")"
        missing=$((missing + 1))
    else
        have=$((have + 1))
    fi
done

if [ "$missing" -eq 0 ]; then
    echo "  none, every chapter has a real screenshot"
fi

if [ "$have" -gt 0 ]; then
    echo ""
    echo "Real screenshots in place:"
    for file in "$DIR"/manual_*.png; do
        [ -e "$file" ] || continue
        grep -q "$MARKER" "$file" 2>/dev/null || echo "  $(basename "$file")"
    done
fi

echo ""
echo "$missing of $((missing + have)) chapters still show a placeholder."
echo "What each one should show: $DOC"
