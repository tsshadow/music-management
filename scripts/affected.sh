#!/bin/bash
# Returns a list of affected modules based on git status and diff

# Global files that trigger a full rebuild
GLOBAL_PATTERNS=(
    "VERSION"
    "requirements.txt"
    "docker/Dockerfile.base"
    "services/common/"
    "modules/music-management/"
    "build.sh"
    "publish.sh"
    "install.sh"
)

# Mapping of paths to modules
MODULE_MAP=(
    "services/ml-analyzer/:ml"
    "services/music_manager/:manager"
    "Dockerfile.music-manager:manager"
    "services/music_manager/frontend/:manager"
    "services/scanner/:scanner"
    "docker/Dockerfile.scanner:scanner"
    "services/tagger/:tagger"
    "docker/Dockerfile.tagger:tagger"
    "services/downloader/telegram/:telegram"
    "docker/Dockerfile.telegram:telegram"
    "services/downloader/:downloader"
    "docker/Dockerfile.downloader:downloader"
    "services/importer/:importer"
    "docker/Dockerfile.importer:importer"
    "frontend/:app"
    "modules/music-management/:app"
    "Dockerfile.music-management:app"
    "tools/:tools"
    "Dockerfile.tools:tools"
)

# Get changed files (including untracked and changes compared to upstream/main)
UPSTREAM=$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null || echo "origin/main")
CHANGED_FILES=$( (git status --porcelain | sed 's/^...//'; git diff --name-only $UPSTREAM...HEAD 2>/dev/null || git diff --name-only HEAD~1 2>/dev/null) | sort -u)

if [ -z "$CHANGED_FILES" ]; then
    # If no changes compared to upstream, check last commit
    CHANGED_FILES=$(git diff --name-only HEAD~1 2>/dev/null)
fi

# Check for global changes
for file in $CHANGED_FILES; do
    for pattern in "${GLOBAL_PATTERNS[@]}"; do
        if [[ $file == "$pattern"* ]]; then
            echo "all"
            exit 0
        fi
    done
done

# Check for module changes
AFFECTED=("manager" "app")
for file in $CHANGED_FILES; do
    for entry in "${MODULE_MAP[@]}"; do
        path="${entry%%:*}"
        module="${entry#*:}"
        if [[ $file == "$path"* ]]; then
            AFFECTED+=("$module")
        fi
    done
done

# Print unique affected modules
RESULT=$(echo "${AFFECTED[@]}" | tr ' ' '\n' | sort -u | tr '\n' ' ')
if [ -z "$RESULT" ]; then
    echo "none"
else
    echo "$RESULT"
fi
