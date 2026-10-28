#!/bin/bash

# MuMa Local Development Script
# This script starts the docker containers locally with development settings:
# - Downloaders and Importer in dry-run mode
# - Empty music folder and database for testing

set -e

# Project root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Force local docker context
export DOCKER_HOST=unix:///var/run/docker.sock

# Load environment variables from .env if it exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Set Dev Credentials (simple for local testing)
export DB_USER="muma"
export DB_PASS="muma"
export MYSQL_ROOT_PASSWORD="root"
export DB_NAME="music-management"
export MUMA_API_KEY="dev-key"
export FIREFOX_PASSWORD="dev"

# Production info (optional for dev, used for image pulling)
PROD_FILE="$PROJECT_ROOT/.production"
if [ -f "$PROD_FILE" ]; then
    DOCKER_USER=$(grep "Docker Hub User" "$PROD_FILE" | awk '{print $NF}')
fi
export DOCKER_USER="${DOCKER_USER:-muma}"

COMMAND=${1:-start}
shift || true

# Parse flags
CLEAN=false
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --clean) CLEAN=true ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

# The source workers are compose profiles; the dev stack runs all of them (up and down).
export COMPOSE_PROFILES="${COMPOSE_PROFILES:-soundcloud,youtube,telegram,importer}"
COMPOSE_FILES="-f docker/docker-compose.yml -f docker/docker-compose.workers.yml -f docker/docker-compose.tools.yml -f docker/docker-compose.dev.yml"

stop_dev() {
    echo "--- Stopping Local Development Environment ---"
    docker-compose $COMPOSE_FILES down --remove-orphans
}

start_dev() {
    echo "--- Preparing Local Development Environment ---"

    # Step 1: Set Dev Environment Variables
    echo "Setting development environment variables..."
    export HOST_DATA_PATH="$PROJECT_ROOT/data/dev"
    export HOST_MUSIC_PATH="$PROJECT_ROOT/data/music"
    export dryrun="True"
    export debug="True"
    export delimiter="/"
    export API_KEY="$MUMA_API_KEY"

    # Container-internal paths for services
    export music_folder_path="/mnt/music"
    export import_folder_path="/mnt/music/import"
    export youtube_folder="/mnt/music/Youtube"
    export soundcloud_folder="/mnt/music/Soundcloud"
    export telegram_folder="/mnt/music/Telegram"
    export eps_folder_path="/mnt/music/EPs"
    export youtube_archive="/mnt/music/archives/youtube"
    export soundcloud_archive="/mnt/music/archives/soundcloud"

    if [ "$CLEAN" = true ]; then
        echo "Clearing local data and music folders..."
        # Use a container to clear files that might have root ownership from previous runs
        docker run --rm -v "$HOST_DATA_PATH":/data-dev -v "$HOST_MUSIC_PATH":/data-music alpine sh -c "rm -rf /data-dev/* /data-music/*" || true
    fi

    # Ensure directories exist
    mkdir -p "$HOST_DATA_PATH" "$HOST_MUSIC_PATH" 
    mkdir -p "$HOST_DATA_PATH/mariadb" "$HOST_DATA_PATH/music-management-server/var/lms" "$HOST_DATA_PATH/alpha-music-management-server/var/lms" "$HOST_DATA_PATH/importer" "$HOST_DATA_PATH/shared" "$HOST_DATA_PATH/firefox"
    mkdir -p "$HOST_MUSIC_PATH/import" "$HOST_MUSIC_PATH/Youtube" "$HOST_MUSIC_PATH/Soundcloud" "$HOST_MUSIC_PATH/Telegram" "$HOST_MUSIC_PATH/EPs" "$HOST_MUSIC_PATH/archives/youtube" "$HOST_MUSIC_PATH/archives/soundcloud" "$HOST_MUSIC_PATH/artists"

    # Set permissions using a container to avoid host permission issues
    echo "Ensuring correct permissions on data and music folders..."
    docker run --rm -v "$HOST_DATA_PATH":/data-dev -v "$HOST_MUSIC_PATH":/data-music alpine sh -c "chmod -R 777 /data-dev /data-music" || true

    # Step 3: Start DB container
    echo "Starting database container..."
    docker-compose -f docker/docker-compose.yml up -d db

    # Wait for DB to be ready
    echo "Waiting for database to be ready..."
    # mariadb-admin, not mysqladmin: the old name is gone in MariaDB 12, and a
    # 127 here would spin this loop forever instead of failing.
    until docker exec music-management-db-1 mariadb-admin ping -h "localhost" --silent; do
        sleep 1
    done

    # Step 4: Start all containers with dev settings
    echo "Starting all containers in DRY RUN mode..."
    export DB_DB="${DB_NAME}"
    export DB_HOST="db"
    export DB_PORT="3306"

    # Use docker-compose up
    docker-compose $COMPOSE_FILES up -d --remove-orphans

    echo "--- Local Development Environment Ready ---"
    echo "Music Manager: http://localhost:8000 (API Key: $MUMA_API_KEY)"
    echo "Spotify UI: http://localhost:5082"
    echo "phpMyAdmin: http://localhost:8002 (User: $DB_USER, Pass: $DB_PASS)"
    echo "Firefox: http://localhost:7003 (Pass: $FIREFOX_PASSWORD)"
    echo ""
    echo "Database Credentials:"
    echo " - Root Password: $MYSQL_ROOT_PASSWORD"
    echo " - DB User: $DB_USER"
    echo " - DB Pass: $DB_PASS"
    echo ""
    echo "Note: Importer and Downloaders are running in DRY RUN mode."
    echo "Usage: $0 {start|stop|restart} [--clean]"
}

case $COMMAND in
    start)
        start_dev
        ;;
    stop)
        stop_dev
        ;;
    restart)
        stop_dev
        start_dev
        ;;
    *)
        echo "Usage: $0 {start|stop|restart} [--clean]"
        exit 1
        ;;
esac
