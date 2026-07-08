#!/bin/bash

# Script to run the artist image fetcher inside the Docker container
# Usage: ./scripts/fetch_artist_images.sh [fetch|fetch-missing|refresh] [args...]

# Find the music-manager container
CONTAINER_NAME=$(docker ps --filter "name=music-manager" --format "{{.Names}}" | head -n 1)

if [ -z "$CONTAINER_NAME" ]; then
    echo "Error: music-manager container not found."
    exit 1
fi

echo "Running artist image fetcher in container: $CONTAINER_NAME"

# Default to fetch-missing if no command provided
COMMAND=${1:-"fetch-missing"}
shift

docker exec -it "$CONTAINER_NAME" python -m services.music_manager.artist_image_fetcher.cli "$COMMAND" "$@"
