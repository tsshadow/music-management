#!/bin/bash
set -e

cd "$(dirname "$0")"
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Ensure variables are set
IMAGE_NAME="${IMAGE_NAME:-muma/lms}"
TAG="${TAG:-alpha}"

echo "Building Docker image ${IMAGE_NAME}:${TAG}..."
docker build -t "${IMAGE_NAME}:${TAG}" -f Dockerfile-release .
