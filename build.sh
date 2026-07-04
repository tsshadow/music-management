#!/bin/bash
set -e

cd "$(dirname "$0")"

# Check for docker permissions
if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Permission denied while trying to connect to the Docker daemon."
    echo "Please ensure your user ($USER) is in the 'docker' group."
    echo "You can add yourself with: sudo usermod -aG docker \$USER"
    echo "Then log out and log back in, or run: newgrp docker"
    exit 1
fi

if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Ensure variables are set
IMAGE_NAME="${IMAGE_NAME}"
TAG="${TAG}"

echo "Building Docker image ${IMAGE_NAME}:${TAG}..."
docker build -t "${IMAGE_NAME}:${TAG}" -f Dockerfile-release .
