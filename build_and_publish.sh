#!/bin/bash
set -e

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

chmod +x scripts/affected.sh
AFFECTED=$(./scripts/affected.sh)

if [ "$AFFECTED" == "none" ]; then
    echo "No changes detected. Skipping build and publish."
    exit 0
fi

if [ "$AFFECTED" == "all" ]; then
    echo "Global changes detected. Building all modules."
    ./build.sh "$@"
    ./publish.sh "$@"
else
    echo "Affected modules: $AFFECTED"
    ./build.sh $AFFECTED "$@"
    ./publish.sh $AFFECTED "$@"
fi

./scripts/deploy.sh "$@"

echo "Build, publish and deploy completed successfully!"
