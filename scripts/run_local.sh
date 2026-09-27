#!/bin/bash

# run_local.sh - Run music-management services locally with Docker-like environment

# Get the project root directory
# .env values are read the way docker-compose reads them (a `#` inside a
# value is not a comment); see scripts/lib/dotenv.sh and bug report 038.
# shellcheck source=scripts/lib/dotenv.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/dotenv.sh"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR" || exit 1

# Load environment variables from .env if it exists
if [ -f .env ]; then
    echo "Loading .env file..."
    dotenv_load .env
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
    frontend)
        echo "Starting frontend dev server (Vite)..."
        cd services/frontend || exit 1
        [ -d node_modules ] || npm install
        npm run dev
        ;;
    lms)
        echo "Starting LMS (music-management-server) locally..."
        LMS_DIR="$ROOT_DIR/services/music-management-server"
        LMS_BUILD_DIR="${LMS_BUILD_DIR:-$LMS_DIR/build}"
        if [ ! -d "$LMS_BUILD_DIR" ]; then
            echo "No build directory found, configuring first (requires the native LMS toolchain - GTest/Boost/Wt/pugixml/... - installed locally; scripts/test/muma-server-unit.sh instead builds/tests LMS inside Docker, since Wt isn't packaged for Debian/Ubuntu)..."
            cmake -S "$LMS_DIR" -B "$LMS_BUILD_DIR" -DCMAKE_BUILD_TYPE=Debug
        fi
        cmake --build "$LMS_BUILD_DIR" -j"$(nproc)" --target lms
        "$LMS_BUILD_DIR/src/lms/lms" --config "$LMS_DIR/conf/lms.conf"
        ;;
    *)
        echo "Usage: $0 {importer|youtube|soundcloud|telegram|tagger|manager|frontend|lms}"
        echo ""
        echo "This script runs the services locally using the same environment variables"
        echo "as defined in docker-compose.yml and .env."
        echo ""
        echo "Note: 'frontend' and 'lms' proxy to/expect 'manager' (port 8000) and each other"
        echo "(see services/frontend/vite.config.js VITE_API_TARGET / VITE_LMS_TARGET);"
        echo "run 'manager' in another terminal first for a full local dev setup."
        exit 1
        ;;
esac
