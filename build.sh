#!/bin/bash
set -e

# Check for docker permissions
if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Permission denied while trying to connect to the Docker daemon."
    echo "Please ensure your user ($USER) is in the 'docker' group."
    echo "You can add yourself with: sudo usermod -aG docker \$USER"
    echo "Then log out and log back in, or run: newgrp docker"
    exit 1
fi

echo "--- Starting build of containers ---"

build_ml() {
    echo "--- Building ML Analyzer ---"
    docker build -t tsshadow/music-management-ml:latest -f services/ml-analyzer/Dockerfile services/ml-analyzer/
}

build_tools() {
    echo "--- Building Tools ---"
    docker build -t tsshadow/music-management-tools:latest -f Dockerfile.tools .
}

build_app() {
    echo "--- Building Main Application (Music Management) ---"
    echo "Note: This build might take a while and requires a stable internet connection for pnpm install."
    docker build -t tsshadow/music-management:latest -f Dockerfile.music-management .
}

if [ $# -eq 0 ]; then
    build_ml
    build_tools
    build_app
else
    for arg in "$@"; do
        case $arg in
            ml) build_ml ;;
            tools) build_tools ;;
            app) build_app ;;
            *) echo "Unknown component: $arg"; exit 1 ;;
        esac
    done
fi

echo "--- Build process completed ---"
