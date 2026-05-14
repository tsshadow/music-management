#!/bin/bash

# Configuration
IMAGE_ML="tsshadow/music-management-ml:latest"
IMAGE_TOOLS="tsshadow/music-management-tools:latest"
IMAGE_APP="tsshadow/music-management:latest"

# Build ML Analyzer
echo "--- Building ML Analyzer ---"
docker build -t "$IMAGE_ML" -f services/ml-analyzer/Dockerfile services/ml-analyzer/
docker push "$IMAGE_ML"

# Build Tools
echo "--- Building Tools ---"
docker build -t "$IMAGE_TOOLS" -f Dockerfile.tools .
docker push "$IMAGE_TOOLS"

# Build Main Application
echo "--- Building Main Application ---"
echo "Note: This build might take a while and requires a stable internet connection for pnpm install."
docker build -t "$IMAGE_APP" -f Dockerfile.music-management .
docker push "$IMAGE_APP"

echo "--- All builds and pushes completed ---"
