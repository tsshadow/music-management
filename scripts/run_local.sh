#!/bin/bash

# run_local.sh - Run music-management services locally with Docker-like environment

# Get the project root directory
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Load environment variables from .env if it exists
if [ -f .env ]; then
    echo "Loading .env file..."
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Strip trailing comments and whitespace
        clean_line=$(echo "$line" | sed 's/[[:space:]]*#.*$//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [[ -n "$clean_line" && ! "$clean_line" =~ ^# ]]; then
            # Use 'export' only if it's a valid assignment
            if [[ "$clean_line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
                export "$clean_line"
            fi
        fi
    done < .env
fi

# Set additional Docker-like environment variables that might be missing from .env
export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/services/downloader"
export rescan="${rescan:-True}"
export dryrun="${dryrun:-False}"
export debug="${debug:-True}"
export delimiter="${delimiter:-/}"

# Default cookies if not set (matches docker-compose defaults but might need local adjustment)
export YT_COOKIES="${YT_COOKIES:-firefox:/firefox-config/profile}"
export soundcloud_cookies="${soundcloud_cookies:-firefox:/firefox-config/profile}"

case "$1" in
    importer)
        echo "Starting Importer Worker..."
        python3 services/importer/importer_service.py --repeat --sleeptime 300
        ;;
    youtube)
        echo "Starting YouTube Worker..."
        python3 services/downloader/downloader_service.py --step youtube --repeat --sleeptime 300 --break-on-existing
        ;;
    soundcloud)
        echo "Starting SoundCloud Worker..."
        python3 services/downloader/downloader_service.py --step soundcloud --repeat --sleeptime 300 --break-on-existing
        ;;
    telegram)
        echo "Starting Telegram Worker..."
        python3 services/downloader/downloader_service.py --step telegram --repeat --sleeptime 300
        ;;
    tagger)
        echo "Starting Tagger Worker..."
        python3 services/tagger/tagger_service.py --repeat --sleeptime 300
        ;;
    manager)
        echo "Starting Music Manager..."
        uvicorn services.music_manager.main:app --host 0.0.0.0 --port 8000 --reload
        ;;
    *)
        echo "Usage: $0 {importer|youtube|soundcloud|telegram|tagger|manager}"
        echo ""
        echo "This script runs the services locally using the same environment variables"
        echo "as defined in docker-compose.yml and .env."
        exit 1
        ;;
esac
