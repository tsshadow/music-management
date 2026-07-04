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

# Check for docker registry authentication
if ! docker info | grep -q "Username:"; then
    echo "WARNING: You don't seem to be logged into Docker Hub."
    echo "Pushing images to 'muma/' will likely fail."
    echo "Please run: docker login"
    echo ""
    read -p "Do you want to continue anyway? (y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

if [ -f .env ]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Strip trailing comments and whitespace
        clean_line=$(echo "$line" | sed 's/[[:space:]]*#.*$//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [[ -n "$clean_line" && ! "$clean_line" =~ ^# ]]; then
            export "$clean_line"
        fi
    done < .env
fi

# Ensure variables are set
IMAGE_NAME="${IMAGE_NAME}"
VERSION=$(grep "project(lms VERSION" CMakeLists.txt | sed 's/.*VERSION \(.*\))/\1/')

# Determine mode (debug is default)
MODE="${1:-${BUILD_MODE:-debug}}"

if [ "$MODE" == "release" ]; then
    ADDITIONAL_TAG="stable"
    echo "Release mode: pushing tag 'stable'"
else
    # Default to debug/alpha
    ADDITIONAL_TAG="latest"
    UNSTABLE_TAG="unstable"
    ALPHA_TAG="alpha"
    echo "Debug mode: pushing tags 'latest', 'unstable' and 'alpha'"
fi

echo "Pushing Docker image ${IMAGE_NAME}:${ADDITIONAL_TAG} and ${IMAGE_NAME}:${VERSION}..."
docker push "${IMAGE_NAME}:${ADDITIONAL_TAG}"
docker push "${IMAGE_NAME}:${VERSION}"
if [ "$MODE" != "release" ]; then
    docker push "${IMAGE_NAME}:${UNSTABLE_TAG}"
    docker push "${IMAGE_NAME}:${ALPHA_TAG}"
fi

echo "--- Push process completed ---"
