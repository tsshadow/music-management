#!/bin/bash
set -e

# Configuration
REMOTE_CONTEXT="remote-lxc"
REMOTE_HOST="root@192.0.2.40"

cd "$(dirname "$(readlink -f "$0")")/.."

echo "Switching to Docker context: $REMOTE_CONTEXT"
docker context use "$REMOTE_CONTEXT"

# Ensure we switch back to default on exit
trap 'docker context use default' EXIT

# Ensure we use host networking because of LXC sysctl restrictions
export DOCKER_FLAGS="--network host"

# Run the requested script (default to build.sh)
if [[ "$(basename "$0")" == "rbup"* || "$1" == "bup" ]]; then
    if [ "$1" == "bup" ]; then shift; fi
    ./scripts/build_and_publish.sh "$@"
elif [ "$1" == "publish" ]; then
    shift
    ./scripts/publish.sh "$@"
else
    ./scripts/build.sh "$@"
fi

echo "Remote execution complete on $REMOTE_HOST"
