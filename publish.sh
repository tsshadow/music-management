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

echo "--- Starting push of containers ---"

if [ -f .env ]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Strip trailing comments and whitespace
        clean_line=$(echo "$line" | sed 's/[[:space:]]*#.*$//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [[ -n "$clean_line" && ! "$clean_line" =~ ^# ]]; then
            export "$clean_line"
        fi
    done < .env
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
VERSION=$(cat VERSION 2>/dev/null || echo "latest")

push_base() {
    echo "--- Pushing Base Image ($VERSION) ---"
    docker push "${DOCKER_USER}/${IMAGE_BASE}:latest"
    docker push "${DOCKER_USER}/${IMAGE_BASE}:${VERSION}"
}

push_scanner() {
    echo "--- Pushing Scanner ($VERSION) ---"
    docker push "${DOCKER_USER}/${IMAGE_SCANNER}:latest"
    docker push "${DOCKER_USER}/${IMAGE_SCANNER}:${VERSION}"
}

push_tagger() {
    echo "--- Pushing Tagger ($VERSION) ---"
    docker push "${DOCKER_USER}/${IMAGE_TAGGER}:latest"
    docker push "${DOCKER_USER}/${IMAGE_TAGGER}:${VERSION}"
}

push_downloader() {
    echo "--- Pushing Downloader ($VERSION) ---"
    docker push "${DOCKER_USER}/${IMAGE_DOWNLOADER}:latest"
    docker push "${DOCKER_USER}/${IMAGE_DOWNLOADER}:${VERSION}"
}

push_telegram() {
    echo "--- Pushing Telegram ($VERSION) ---"
    docker push "${DOCKER_USER}/${IMAGE_TELEGRAM}:latest"
    docker push "${DOCKER_USER}/${IMAGE_TELEGRAM}:${VERSION}"
}

push_importer() {
    echo "--- Pushing Importer ($VERSION) ---"
    docker push "${DOCKER_USER}/${IMAGE_IMPORTER}:latest"
    docker push "${DOCKER_USER}/${IMAGE_IMPORTER}:${VERSION}"
}

push_rating() {
    echo "--- Pushing Rating System ($VERSION) ---"
    docker push "${DOCKER_USER}/${IMAGE_RATING}:latest"
    docker push "${DOCKER_USER}/${IMAGE_RATING}:${VERSION}"
}

push_ml() {
    echo "--- Pushing ML Analyzer ($VERSION) ---"
    docker push "${DOCKER_USER}/${IMAGE_ML}:latest"
    docker push "${DOCKER_USER}/${IMAGE_ML}:${VERSION}"
}

push_tools() {
    echo "--- Pushing Tools ($VERSION) ---"
    docker push "${DOCKER_USER}/${IMAGE_TOOLS}:latest"
    docker push "${DOCKER_USER}/${IMAGE_TOOLS}:${VERSION}"
}

push_app() {
    echo "--- Pushing Main Application ($VERSION) ---"
    docker push "${DOCKER_USER}/${IMAGE_APP}:latest"
    docker push "${DOCKER_USER}/${IMAGE_APP}:${VERSION}"
}

push_management() {
    echo "--- Pushing Management API ($VERSION) ---"
    docker push "${DOCKER_USER}/${IMAGE_MANAGEMENT}:latest"
    docker push "${DOCKER_USER}/${IMAGE_MANAGEMENT}:${VERSION}"
}

if [ $# -eq 0 ]; then
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
    wait
else
    echo "--- Pushing requested modules: $@ ---"
    for arg in "$@"; do
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
            base) push_base & ;;
            *) echo "Unknown component: $arg"; exit 1 ;;
        esac
    done
    wait
fi

echo "--- Push process completed ---"
