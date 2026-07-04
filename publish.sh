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

push_ml() {
    docker push tsshadow/music-management-ml:latest
}

push_tools() {
    docker push tsshadow/music-management-tools:latest
}

push_app() {
    docker push tsshadow/music-management:latest
}

if [ $# -eq 0 ]; then
    push_ml
    push_tools
    push_app
else
    for arg in "$@"; do
        case $arg in
            ml) push_ml ;;
            tools) push_tools ;;
            app) push_app ;;
            *) echo "Unknown component: $arg"; exit 1 ;;
        esac
    done
fi

echo "--- Push process completed ---"
