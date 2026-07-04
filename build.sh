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

if [ -f .env ]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ ! "$line" =~ ^# && -n "$line" ]]; then
            export "$line"
        fi
    done < .env
fi

# Configuration
DOCKER_USER="${DOCKER_USER}"
IMAGE_ML="${IMAGE_ML}"
IMAGE_TOOLS="${IMAGE_TOOLS}"
IMAGE_APP="${IMAGE_APP}"
IMAGE_MANAGEMENT="${IMAGE_MANAGEMENT}"
VERSION=$(cat VERSION 2>/dev/null || echo "latest")

build_ml() {
    echo "--- Building ML Analyzer ($VERSION) ---"
    docker build -t "${DOCKER_USER}/${IMAGE_ML}:latest" -t "${DOCKER_USER}/${IMAGE_ML}:${VERSION}" -f services/ml-analyzer/Dockerfile services/ml-analyzer/
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
    echo "--- Building Management API ($VERSION) ---"
    docker build -t "${DOCKER_USER}/${IMAGE_MANAGEMENT}:latest" -t "${DOCKER_USER}/${IMAGE_MANAGEMENT}:${VERSION}" -f Dockerfile.management-api .
}

if [ $# -eq 0 ]; then
    build_ml
    build_tools
    build_app
    build_management
else
    for arg in "$@"; do
        case $arg in
            ml) build_ml ;;
            tools) build_tools ;;
            app) build_app ;;
            mgmt|management) build_management ;;
            *) echo "Unknown component: $arg"; exit 1 ;;
        esac
    done
fi

echo "--- Build process completed ---"
