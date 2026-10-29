#!/bin/bash
# .env values are read the way docker-compose reads them (a `#` inside a
# value is not a comment); see scripts/lib/dotenv.sh and bug report 038.
# shellcheck source=scripts/lib/dotenv.sh
. "$(dirname "${BASH_SOURCE[0]}")/../../../scripts/lib/dotenv.sh"
set -e

cd "$(dirname "$(readlink -f "$0")")/.."

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

# Handle --remote flag
REMOTE=false
for arg in "$@"; do
    if [ "$arg" == "--remote" ]; then
        REMOTE=true
        break
    fi
done

if [ "$REMOTE" == "true" ]; then
    # Remove --remote from arguments
    NEW_ARGS=()
    for arg in "$@"; do
        if [ "$arg" != "--remote" ]; then
            NEW_ARGS+=("$arg")
        fi
    done
    
    # Check if we are already in the remote context to avoid recursion
    CURRENT_CONTEXT=$(docker context show)
    if [ "$CURRENT_CONTEXT" != "remote-lxc" ]; then
        echo "=== OFFLOADING PUSH TO REMOTE LXC ==="
        if [ ! -x ./scripts/remote-build.sh ]; then
            echo "--remote needs scripts/remote-build.sh, which lives in the private muma-ops repository" >&2
            echo "(run its install.sh to link it), or build without --remote." >&2
            exit 1
        fi
        exec ./scripts/remote-build.sh publish "${NEW_ARGS[@]}"
    fi
    
    # Apply new args (without --remote) for local execution (inside remote context)
    set -- "${NEW_ARGS[@]}"
fi

if [ -f .env ]; then
    dotenv_load .env --keep-existing
fi

# Ensure variables are set
export IMAGE_NAME="${IMAGE_NAME}"
VERSION=$(grep "project(lms VERSION" CMakeLists.txt | sed 's/.*VERSION \(.*\))/\1/')

# Determine mode (debug is default)
MODE="${1:-${BUILD_MODE:-debug}}"

if [ "$MODE" == "release" ]; then
    ADDITIONAL_TAG="latest"
    STABLE_TAG="stable"
    echo "Release mode: pushing tags 'latest' and 'stable'"
else
    # Default to debug/alpha
    ADDITIONAL_TAG="alpha"
    UNSTABLE_TAG="unstable"
    echo "Debug mode: pushing tags 'alpha' and 'unstable'"
fi

echo "Pushing Docker image ${IMAGE_NAME}:${ADDITIONAL_TAG} and ${IMAGE_NAME}:${VERSION}..."
docker push "${IMAGE_NAME}:${ADDITIONAL_TAG}"
docker push "${IMAGE_NAME}:${VERSION}"
if [ "$MODE" == "release" ]; then
    docker push "${IMAGE_NAME}:${STABLE_TAG}"
else
    docker push "${IMAGE_NAME}:${UNSTABLE_TAG}"
fi

./scripts/deploy.sh "$MODE"

echo "--- Push and deploy process completed ---"
