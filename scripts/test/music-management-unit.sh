#!/bin/bash
# scripts/test/music-management-unit.sh  
# Runs the Python unit tests for music_manager, tagger, scanner, importer and downloader.
# Usage: ./scripts/test/music-management-unit.sh [pytest-args...]

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

# Load .env if it exists (same convention as build.sh / scripts/lint.sh)
if [ -f .env ]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        clean_line=$(echo "$line" | sed 's/[[:space:]]*#.*$//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [[ -n "$clean_line" && "$clean_line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
            export "$clean_line"
        fi
    done < .env
fi

export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/services:$PYTHONPATH"

# Known-good test targets (see docs/testing-inventory.md for details per module).
TEST_TARGETS=(
    "services/music_manager/tests/"
    "services/importer/tests/"
    "services/downloader/soundcloud/tests/"
    "services/tests/YoutubeDownloaderTest.py"
    "services/tests/YoutubeSongTest.py"
    "services/tests/YoutubeSongProcessorTest.py"
    "services/tests/YoutubeArchiveTest.py"
    "services/tests/TelegramDownloaderTest.py"
)

echo "--- Running music-management Python unit tests ---"
python3 -m pytest -p no:warnings \
    --cov=services \
    --cov-report=term \
    --cov-report=xml:coverage-python.xml \
    "${TEST_TARGETS[@]}" "$@"

# Fix paths in Cobertura XML for GitLab visualization
# It changes filename="path/to/file" to filename="services/path/to/file"
# and sets <source> to the project root.
if [ -f coverage-python.xml ]; then
    echo "--- Fixing paths in coverage-python.xml ---"
    sed -i 's|filename="|filename="services/|g' coverage-python.xml
    sed -i 's|<source>.*</source>|<source>./</source>|g' coverage-python.xml
fi
