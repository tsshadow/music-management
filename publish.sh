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
    push_ml
    push_tools
    push_app
    push_management
else
    for arg in "$@"; do
        case $arg in
            ml) push_ml ;;
            tools) push_tools ;;
            app) push_app ;;
            mgmt|management) push_management ;;
            *) echo "Unknown component: $arg"; exit 1 ;;
        esac
    done
fi

echo "--- Push process completed ---"
