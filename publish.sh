#!/bin/bash
set -e

# Check for docker permissions
if ! docker info >/dev/null 2>&1; then
    if [ -z "$DOCKER_GROUP_RETRY" ] && getent group docker | grep -q "\b$USER\b"; then
        export DOCKER_GROUP_RETRY=1
        echo "Detected 'docker' group membership but it's not active in this session."
        echo "Re-executing with 'sg docker'..."
        CMD=$(printf "%q " "$0" "$@")
        exec sg docker -c "$CMD"
    fi
    echo "ERROR: Permission denied while trying to connect to the Docker daemon."
    echo "Please ensure your user ($USER) is in the 'docker' group."
    echo "You can add yourself with: sudo usermod -aG docker \$USER"
    echo "Then log out and log back in, or run: newgrp docker"
    exit 1
fi

# Check for docker registry authentication
if ! docker info | grep -q "Username:"; then
    echo "WARNING: You don't seem to be logged into Docker Hub."
    echo "Pushing images to 'tsshadow/' will likely fail."
    echo "Please run: docker login"
    echo ""
    read -p "Do you want to continue anyway? (y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Load environment variables
if [ -f .env ]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Strip trailing comments and whitespace
        clean_line=$(echo "$line" | sed 's/[[:space:]]*#.*$//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [[ -n "$clean_line" && ! "$clean_line" =~ ^# ]]; then
            export "$clean_line"
        fi
    done < .env
fi

# Helper function to run SSH command
run_ssh() {
    local host="$1"
    local user="$2"
    local pass="$3"
    local cmd="$4"
    
    if [ -z "$host" ] || [ -z "$user" ]; then
        return 1
    fi

    if [ -z "$pass" ]; then
        ssh -o StrictHostKeyChecking=no "${user}@${host}" "${cmd}"
    elif command -v sshpass >/dev/null 2>&1; then
        sshpass -p "${pass}" ssh -o StrictHostKeyChecking=no "${user}@${host}" "${cmd}"
    else
        echo "Error: sshpass not found. Install it or unset password variable."
        exit 1
    fi
}


echo "--- Starting push of containers ---"

DEBUG_MODE=false
REMOTE_MODE=false
SEMI_REMOTE_MODE=false
for arg in "$@"; do
    if [ "$arg" == "--debug" ]; then
        DEBUG_MODE=true
    elif [ "$arg" == "--remote" ]; then
        REMOTE_MODE=true
    elif [ "$arg" == "--semi-remote" ]; then
        SEMI_REMOTE_MODE=true
    fi
done

if [ "$REMOTE_MODE" = true ] && [ "$SEMI_REMOTE_MODE" = true ]; then
    echo "ERROR: Cannot use both --remote and --semi-remote"
    exit 1
fi

if [ "$DEBUG_MODE" = true ]; then
    echo "--- Debug mode enabled ---"
    set -x
fi

# Create pre-deployment database backup (Release only)
if [ "$DEBUG_MODE" = false ] && [ -n "${REMOTE_HOST}" ] && [ -n "${REMOTE_USER}" ]; then
    echo "--- Creating pre-deployment database backup on ${REMOTE_HOST} ---"
    BACKUP_CMD="
        if docker ps --format '{{.Names}}' | grep -q 'music-management-db-1'; then
            mkdir -p /muma/backups
            BACKUP_FILE=\"/muma/backups/muma_backup_\$(date +%Y%m%d_%H%M%S).sql\"
            docker exec music-management-db-1 /usr/bin/mysqldump --single-transaction --quick -u root --password=\"$MYSQL_ROOT_PASSWORD\" \"$DB_DB\" > \"\$BACKUP_FILE\"
            gzip \"\$BACKUP_FILE\"
            echo \"Backup saved to \${BACKUP_FILE}.gz\"
        else
            echo \"Warning: music-management-db-1 container not found, skipping backup.\"
        fi
    "
    run_ssh "$REMOTE_HOST" "$REMOTE_USER" "$REMOTE_PASS" "$BACKUP_CMD" || echo "Warning: Remote backup failed."
fi

# Configuration
DOCKER_USER="${DOCKER_USER}"
IMAGE_ML="${IMAGE_ML}"
IMAGE_TOOLS="${IMAGE_TOOLS}"
IMAGE_APP="${IMAGE_APP}"
IMAGE_MANAGEMENT="${IMAGE_MANAGEMENT}"
IMAGE_BASE="${IMAGE_BASE}"
IMAGE_SCANNER="${IMAGE_SCANNER}"
IMAGE_TAGGER="${IMAGE_TAGGER}"
IMAGE_DOWNLOADER="${IMAGE_DOWNLOADER}"
IMAGE_TELEGRAM="${IMAGE_TELEGRAM}"
IMAGE_IMPORTER="${IMAGE_IMPORTER}"
IMAGE_RATING="${IMAGE_RATING}"
IMAGE_SCROBBLE="${IMAGE_SCROBBLE}"
IMAGE_USER="${IMAGE_USER}"
IMAGE_STATS="${IMAGE_STATS}"
VERSION=$(cat VERSION 2>/dev/null || echo "latest")

# Docker command configuration
DOCKER_CMD="docker"
if [ "$REMOTE_MODE" = true ]; then
    echo "--- Remote push mode enabled ---"
    DOCKER_CMD="docker -c remote-lxc"
fi

push_base() {
    echo "--- Pushing Base Image ($VERSION) ---"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_BASE}:latest"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_BASE}:${VERSION}"
}

push_scanner() {
    echo "--- Pushing Scanner ($VERSION) ---"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_SCANNER}:latest"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_SCANNER}:${VERSION}"
}

push_tagger() {
    echo "--- Pushing Tagger ($VERSION) ---"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_TAGGER}:latest"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_TAGGER}:${VERSION}"
}

push_downloader() {
    echo "--- Pushing Downloader ($VERSION) ---"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_DOWNLOADER}:latest"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_DOWNLOADER}:${VERSION}"
}

push_telegram() {
    echo "--- Pushing Telegram ($VERSION) ---"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_TELEGRAM}:latest"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_TELEGRAM}:${VERSION}"
}

push_importer() {
    echo "--- Pushing Importer ($VERSION) ---"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_IMPORTER}:latest"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_IMPORTER}:${VERSION}"
}

push_rating() {
    echo "--- Pushing Rating System ($VERSION) ---"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_RATING}:latest"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_RATING}:${VERSION}"
}

push_scrobble() {
    echo "--- Pushing Scrobble Service ($VERSION) ---"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_SCROBBLE}:latest"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_SCROBBLE}:${VERSION}"
}

push_user() {
    echo "--- Pushing User Service ($VERSION) ---"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_USER}:latest"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_USER}:${VERSION}"
}

push_stats() {
    echo "--- Pushing Stats Service ($VERSION) ---"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_STATS}:latest"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_STATS}:${VERSION}"
}

push_ml() {
    local cmd=$DOCKER_CMD
    if [ "$SEMI_REMOTE_MODE" = true ]; then cmd="docker -c remote-lxc"; fi
    echo "--- Pushing ML Analyzer ($VERSION) ---"
    $cmd push "${DOCKER_USER}/${IMAGE_ML}:latest"
    $cmd push "${DOCKER_USER}/${IMAGE_ML}:${VERSION}"
}

push_tools() {
    local cmd=$DOCKER_CMD
    if [ "$SEMI_REMOTE_MODE" = true ]; then cmd="docker -c remote-lxc"; fi
    echo "--- Pushing Tools ($VERSION) ---"
    $cmd push "${DOCKER_USER}/${IMAGE_TOOLS}:latest"
    $cmd push "${DOCKER_USER}/${IMAGE_TOOLS}:${VERSION}"
}

push_app() {
    local cmd=$DOCKER_CMD
    if [ "$SEMI_REMOTE_MODE" = true ]; then cmd="docker -c remote-lxc"; fi
    echo "--- Pushing Main Application ($VERSION) ---"
    $cmd push "${DOCKER_USER}/${IMAGE_APP}:latest"
    $cmd push "${DOCKER_USER}/${IMAGE_APP}:${VERSION}"
}

push_management() {
    echo "--- Pushing Management API ($VERSION) ---"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_MANAGEMENT}:latest"
    $DOCKER_CMD push "${DOCKER_USER}/${IMAGE_MANAGEMENT}:${VERSION}"
}

# Filter arguments to remove special flags
REQUESTED_MODULES=()
for arg in "$@"; do
    case $arg in
        --debug|--remote|--semi-remote|patch) ;;
        *) REQUESTED_MODULES+=("$arg") ;;
    esac
done

if [ "$SEMI_REMOTE_MODE" = true ]; then
    echo "--- Semi-remote push mode enabled ---"
    echo "--- Pushing ML, Tools, and App from remote, others local ---"
fi

if [ ${#REQUESTED_MODULES[@]} -eq 0 ]; then
    echo "--- Pushing all modules in parallel ---"
    push_ml &
    push_tools &
    push_management &
    push_base &
    push_scanner &
    push_tagger &
    push_downloader &
    push_telegram &
    push_importer &
    push_rating &
    push_scrobble &
    push_user &
    push_stats &
    wait
else
    echo "--- Pushing requested modules: ${REQUESTED_MODULES[*]} ---"
    for arg in "${REQUESTED_MODULES[@]}"; do
        case $arg in
            ml) push_ml & ;;
            tools) push_tools & ;;
            app) push_app & ;;
            mgmt|management) push_management & ;;
            scanner) push_scanner & ;;
            tagger) push_tagger & ;;
            downloader) push_downloader & ;;
            telegram) push_telegram & ;;
            importer) push_importer & ;;
            rating) push_rating & ;;
            scrobble) push_scrobble & ;;
            user) push_user & ;;
            stats) push_stats & ;;
            base) push_base & ;;
            *) echo "Unknown component: $arg"; exit 1 ;;
        esac
    done
    wait
fi

echo "--- Push process completed ---"
