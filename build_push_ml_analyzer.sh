#!/bin/bash
set -e

# Configuration
IMAGE_ML="tsshadow/music-management-ml:latest"

# Build ML Analyzer
echo "--- Building ML Analyzer ---"
docker build -t "$IMAGE_ML" -f services/ml-analyzer/Dockerfile services/ml-analyzer/
docker push "$IMAGE_ML"

echo "--- Build and push of $IMAGE_ML completed ---"
