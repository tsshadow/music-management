#!/bin/bash
set -e

# bump [major|minor|patch]
TYPE=${1:-patch}
CDIR="$(dirname "$(readlink -f "$0")")"
ROOT="$CDIR/.."

cd "$ROOT"

# Extract current version
CURRENT_VERSION=$(grep "project(lms VERSION" CMakeLists.txt | sed 's/.*VERSION \(.*\))/\1/')

if [ -z "$CURRENT_VERSION" ]; then
    echo "ERROR: Could not find current version in CMakeLists.txt"
    exit 1
fi

IFS='.' read -r -a VERSION_PARTS <<< "$CURRENT_VERSION"
MAJOR="${VERSION_PARTS[0]}"
MINOR="${VERSION_PARTS[1]}"
PATCH="${VERSION_PARTS[2]}"

if [ "$TYPE" == "major" ]; then
    MAJOR=$((MAJOR + 1))
    MINOR=0
    PATCH=0
elif [ "$TYPE" == "minor" ]; then
    MINOR=$((MINOR + 1))
    PATCH=0
elif [ "$TYPE" == "patch" ]; then
    PATCH=$((PATCH + 1))
else
    echo "Usage: $0 [major|minor|patch]"
    exit 1
fi

NEW_VERSION="$MAJOR.$MINOR.$PATCH"
DATE=$(date +%Y-%m-%d)

echo "Bumping version from $CURRENT_VERSION to $NEW_VERSION..."

# 1. Update CMakeLists.txt
sed -i "s/project(lms VERSION $CURRENT_VERSION)/project(lms VERSION $NEW_VERSION)/" CMakeLists.txt

# 2. Update CHANGELOG.md
# We move Unreleased content to the new version and reset Unreleased
sed -i "s/## \[Unreleased\]/## [Unreleased]\n\n## [$NEW_VERSION] - $DATE/" CHANGELOG.md

# 3. Update RELEASE_NOTES.md
if [ -f "RELEASE_NOTES.md" ]; then
    sed -i "s/Release Notes - LMS $CURRENT_VERSION/Release Notes - LMS $NEW_VERSION/" RELEASE_NOTES.md
    sed -i "s/## Version $CURRENT_VERSION/## Version $NEW_VERSION/" RELEASE_NOTES.md
fi

# 4. Update UI release-notes.json
JSON_FILE="src/lms/ui/public/release-notes.json"
if [ -f "$JSON_FILE" ]; then
    # Prepend new version entry to the JSON array
    TEMP_JSON=$(mktemp)
    echo "[" > "$TEMP_JSON"
    echo "  {" >> "$TEMP_JSON"
    echo "    \"version\": \"$NEW_VERSION\"," >> "$TEMP_JSON"
    echo "    \"date\": \"$DATE\"," >> "$TEMP_JSON"
    echo "    \"notes\": {" >> "$TEMP_JSON"
    echo "      \"Added\": [" >> "$TEMP_JSON"
    echo "        \"New version started.\"" >> "$TEMP_JSON"
    echo "      ]" >> "$TEMP_JSON"
    echo "    }" >> "$TEMP_JSON"
    echo "  }," >> "$TEMP_JSON"
    # Append the rest of the original file starting from the second line
    tail -n +2 "$JSON_FILE" >> "$TEMP_JSON"
    mv "$TEMP_JSON" "$JSON_FILE"
fi

# 5. Git commit and tag
echo "Committing version bump..."
git add CMakeLists.txt CHANGELOG.md
if [ -f "RELEASE_NOTES.md" ]; then git add RELEASE_NOTES.md; fi
if [ -f "$JSON_FILE" ]; then git add "$JSON_FILE"; fi

git commit -m "Bump version to $NEW_VERSION" --trailer "Co-authored-by: Junie <junie@jetbrains.com>"

echo "Creating tag v$NEW_VERSION..."
git tag "v$NEW_VERSION"

echo "Pushing changes and tag..."
git push origin "$(git rev-parse --abbrev-ref HEAD)"
git push origin "v$NEW_VERSION"

echo "Successfully bumped to $NEW_VERSION and pushed tag."
