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
        echo "=== OFFLOADING TO REMOTE LXC ==="
        exec ./scripts/remote-build.sh bup "${NEW_ARGS[@]}"
    fi
    
    # Apply new args (without --remote) for local execution (inside remote context)
    set -- "${NEW_ARGS[@]}"
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

echo "Build, publish and deploy completed successfully!"
