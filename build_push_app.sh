#!/bin/bash
set -e

# Configuration
IMAGE_APP="tsshadow/music-management:latest"

# Build Main Application
echo "--- Building Main Application (Music Management) ---"
echo "Note: This build might take a while and requires a stable internet connection for pnpm install."
docker build -t "$IMAGE_APP" -f Dockerfile.music-management .
docker push "$IMAGE_APP"

echo "--- Build and push of $IMAGE_APP completed ---"
