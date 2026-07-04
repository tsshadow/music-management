#!/bin/bash
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
fi

# Determine mode (debug is default)
MODE="${1:-debug}"

if [ "$MODE" == "release" ]; then
    echo "=== RUNNING IN RELEASE MODE ==="
else
    echo "=== RUNNING IN DEBUG MODE ==="
fi

./scripts/build.sh "$MODE"
./scripts/publish.sh "$MODE"
./scripts/deploy.sh "$MODE"

echo "Build, publish and deploy completed successfully!"
