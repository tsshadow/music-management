#!/bin/bash
set -e

# Configuration
IMAGE_TOOLS="tsshadow/music-management-tools:latest"

# Build Tools
echo "--- Building Tools ---"
docker build -t "$IMAGE_TOOLS" -f Dockerfile.tools .
docker push "$IMAGE_TOOLS"

echo "--- Build and push of $IMAGE_TOOLS completed ---"
