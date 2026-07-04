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

    echo "--- Starting build of containers ---"
    
    DEBUG_MODE=false
    for arg in "$@"; do
        if [ "$arg" == "--debug" ]; then
            DEBUG_MODE=true
            break
        fi
    done

    if [ "$DEBUG_MODE" = true ]; then
        echo "--- Debug mode enabled ---"
        set -x
    fi

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

build_base() {
    echo "--- Building Base Image ($VERSION) ---"
    docker build -t "${DOCKER_USER}/${IMAGE_BASE}:latest" -t "${DOCKER_USER}/${IMAGE_BASE}:${VERSION}" -f docker/Dockerfile.base .
}

build_scanner() {
    build_base
    echo "--- Building Scanner ($VERSION) ---"
    docker build --build-arg DOCKER_USER="${DOCKER_USER}" --build-arg VERSION="${VERSION}" -t "${DOCKER_USER}/${IMAGE_SCANNER}:latest" -t "${DOCKER_USER}/${IMAGE_SCANNER}:${VERSION}" -f docker/Dockerfile.scanner .
}

build_tagger() {
    build_base
    echo "--- Building Tagger ($VERSION) ---"
    docker build --build-arg DOCKER_USER="${DOCKER_USER}" --build-arg VERSION="${VERSION}" -t "${DOCKER_USER}/${IMAGE_TAGGER}:latest" -t "${DOCKER_USER}/${IMAGE_TAGGER}:${VERSION}" -f docker/Dockerfile.tagger .
}

build_downloader() {
    build_base
    echo "--- Building Downloader ($VERSION) ---"
    docker build --build-arg DOCKER_USER="${DOCKER_USER}" --build-arg VERSION="${VERSION}" -t "${DOCKER_USER}/${IMAGE_DOWNLOADER}:latest" -t "${DOCKER_USER}/${IMAGE_DOWNLOADER}:${VERSION}" -f docker/Dockerfile.downloader .
}

build_telegram() {
    build_base
    echo "--- Building Telegram ($VERSION) ---"
    docker build --build-arg DOCKER_USER="${DOCKER_USER}" --build-arg VERSION="${VERSION}" -t "${DOCKER_USER}/${IMAGE_TELEGRAM}:latest" -t "${DOCKER_USER}/${IMAGE_TELEGRAM}:${VERSION}" -f docker/Dockerfile.telegram .
}

build_importer() {
    build_base
    echo "--- Building Importer ($VERSION) ---"
    docker build --build-arg DOCKER_USER="${DOCKER_USER}" --build-arg VERSION="${VERSION}" -t "${DOCKER_USER}/${IMAGE_IMPORTER}:latest" -t "${DOCKER_USER}/${IMAGE_IMPORTER}:${VERSION}" -f docker/Dockerfile.importer .
}

build_rating() {
    build_base
    echo "--- Building Rating System ($VERSION) ---"
    docker build --build-arg DOCKER_USER="${DOCKER_USER}" --build-arg VERSION="${VERSION}" -t "${DOCKER_USER}/${IMAGE_RATING}:latest" -t "${DOCKER_USER}/${IMAGE_RATING}:${VERSION}" -f docker/Dockerfile.rating-system .
}

build_ml() {
    echo "--- Building ML Analyzer ($VERSION) ---"
    docker build -t "${DOCKER_USER}/${IMAGE_ML}:latest" -t "${DOCKER_USER}/${IMAGE_ML}:${VERSION}" -f services/ml-analyzer/Dockerfile .
}

build_tools() {
    echo "--- Building Tools ($VERSION) ---"
    docker build -t "${DOCKER_USER}/${IMAGE_TOOLS}:latest" -t "${DOCKER_USER}/${IMAGE_TOOLS}:${VERSION}" -f Dockerfile.tools .
}

build_app() {
    echo "--- Building Main Application ($VERSION) ---"
    echo "Note: This build might take a while and requires a stable internet connection for pnpm install."
    docker build -t "${DOCKER_USER}/${IMAGE_APP}:latest" -t "${DOCKER_USER}/${IMAGE_APP}:${VERSION}" -f Dockerfile.music-management .
}

build_management() {
    build_base
    echo "--- Building Management API ($VERSION) ---"
    docker build --build-arg DOCKER_USER="${DOCKER_USER}" --build-arg VERSION="${VERSION}" -t "${DOCKER_USER}/${IMAGE_MANAGEMENT}:latest" -t "${DOCKER_USER}/${IMAGE_MANAGEMENT}:${VERSION}" -f Dockerfile.management-api .
}

if [ $# -eq 0 ]; then
    echo "--- Building all modules in parallel ---"
    # Group 1: Independent builds
    build_ml &
    build_tools &
    build_app &
    
    # Group 2: Base-dependent builds
    build_base
    
    build_management &
    build_scanner &
    build_tagger &
    build_downloader &
    build_telegram &
    build_importer &
    build_rating &
    
    wait
else
    echo "--- Building requested modules: $@ ---"
    # If base is needed by any of the requested modules, build it once first
    NEED_BASE=false
    for arg in "$@"; do
        case $arg in
            scanner|tagger|downloader|telegram|importer|rating|mgmt|management) NEED_BASE=true ;;
        esac
    done
    
    if [ "$NEED_BASE" = true ]; then
        build_base
    fi

    for arg in "$@"; do
        case $arg in
            ml) build_ml & ;;
            tools) build_tools & ;;
            app) build_app & ;;
            mgmt|management) build_management & ;;
            scanner) build_scanner & ;;
            tagger) build_tagger & ;;
            downloader) build_downloader & ;;
            telegram) build_telegram & ;;
            importer) build_importer & ;;
            rating) build_rating & ;;
            base) ;; # Already built if needed
            --debug) ;; # Handled at start
            *) echo "Unknown component: $arg"; exit 1 ;;
        esac
    done
    wait
fi

echo "--- Build process completed ---"
