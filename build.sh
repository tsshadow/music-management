#!/bin/bash
set -e

cd "$(dirname "$0")"

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

if [ -f .env ]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ ! "$line" =~ ^# && -n "$line" ]]; then
            export "$line"
        fi
    done < .env
fi

# Ensure variables are set
IMAGE_NAME="${IMAGE_NAME}"
VERSION=$(grep "project(lms VERSION" CMakeLists.txt | sed 's/.*VERSION \(.*\))/\1/')

echo "Building Docker image ${IMAGE_NAME}:latest and ${IMAGE_NAME}:${VERSION}..."
docker build -t "${IMAGE_NAME}:latest" -t "${IMAGE_NAME}:${VERSION}" -f Dockerfile-release .
