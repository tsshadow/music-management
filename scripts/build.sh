#!/bin/bash
set -e

cd "$(dirname "$(readlink -f "$0")")/.."

# Always copy styleguide to ultrasonic if it exists
if [ -d ~/git/ultrasonic/ ]; then
    echo "Copying STYLEGUIDE.md to ~/git/ultrasonic/..."
    cp src/lms/ui/spotify-ui/STYLEGUIDE.md ~/git/ultrasonic/STYLEGUIDE.md
fi

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
        echo "=== OFFLOADING BUILD TO REMOTE LXC ==="
        exec ./scripts/remote-build.sh "${NEW_ARGS[@]}"
    fi
    
    # Apply new args (without --remote) for local execution (inside remote context)
    set -- "${NEW_ARGS[@]}"
fi

if [ -f .env ]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Strip trailing comments and whitespace
        clean_line=$(echo "$line" | sed 's/[[:space:]]*#.*$//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [[ -n "$clean_line" && ! "$clean_line" =~ ^# ]]; then
            varname="${clean_line%%=*}"
            if [ -z "${!varname}" ]; then
                export "$clean_line"
            fi
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
    echo "Release mode: using tag 'stable'"
else
    # Default to debug/alpha
    ADDITIONAL_TAG="latest"
    UNSTABLE_TAG="unstable"
    ALPHA_TAG="alpha"
    echo "Debug mode: using tags 'latest', 'unstable' and 'alpha'"
fi

echo "Building Docker image ${IMAGE_NAME}:${ADDITIONAL_TAG} and ${IMAGE_NAME}:${VERSION}..."
if [ "$MODE" == "release" ]; then
    docker build ${DOCKER_FLAGS} -t "${IMAGE_NAME}:${ADDITIONAL_TAG}" -t "${IMAGE_NAME}:${VERSION}" -f Dockerfile-release .
else
    docker build ${DOCKER_FLAGS} -t "${IMAGE_NAME}:${ADDITIONAL_TAG}" -t "${IMAGE_NAME}:${UNSTABLE_TAG}" -t "${IMAGE_NAME}:${ALPHA_TAG}" -t "${IMAGE_NAME}:${VERSION}" -f Dockerfile-release .
fi
