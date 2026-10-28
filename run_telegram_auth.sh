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
    echo "ERROR: Permission denied while trying to connect to the Docker daemon."
    echo "Please ensure your user ($USER) is in the 'docker' group."
    echo "You can add yourself with: sudo usermod -aG docker \$USER"
    echo "Then log out and log back in, or run: newgrp docker"
    exit 1
fi

# Telegram Authentication Helper Script
# This script helps with the one-time interactive authentication for Telegram.

# Default channel if none provided
CHANNEL=${1:-"Hard Dance Events"}

# The compose file that defines telegram_worker as deployed. It used to point at a
# work-context/docker-compose.yml that no longer exists. docker/docker-compose.workers.yml
# (the local-only overlay scripts/dev.sh layers on top) is not usable on its own here:
# its telegram_worker depends on a `db` service only docker-compose.yml defines.
COMPOSE_FILE_PATH="docker/docker-compose.yml"

# Check if we are in the project root
if [ ! -f "$COMPOSE_FILE_PATH" ]; then
    echo "Error: $COMPOSE_FILE_PATH not found."
    echo "Please run this script from the music-management project root."
    exit 1
fi

# The project .env sits in the repository root; compose would otherwise look for it next to
# the compose file, in docker/.
ENV_ARGS=()
if [ -f ".env" ]; then
    ENV_ARGS=(--env-file .env)
fi

# Detect Docker Compose version
if docker compose version >/dev/null 2>&1; then
    DOCKER_CMD="docker compose"
    echo "Using 'docker compose' (V2)"
elif command -v docker-compose >/dev/null 2>&1; then
    DOCKER_CMD="docker-compose"
    echo "Using 'docker-compose' (V1)"
else
    echo "Error: Docker Compose not found. Please install docker-compose or the docker-compose-plugin."
    exit 1
fi

echo "--- Starting Telegram Authentication for channel: $CHANNEL ---"
echo "Follow the prompts to enter your phone number and the code you receive via Telegram."
echo "The session will be saved in the persistent volume."
echo ""

# Interactive with a TTY by default for `run`; --no-deps leaves the database container alone.
$DOCKER_CMD "${ENV_ARGS[@]}" -f "$COMPOSE_FILE_PATH" --profile telegram run --rm --no-deps telegram_worker \
    python services/downloader/downloader_service.py --step telegram --account "$CHANNEL"

echo ""
echo "--- Authentication Complete ---"
echo "You can now start the worker in the background using:"
echo "$DOCKER_CMD ${ENV_ARGS[*]} -f $COMPOSE_FILE_PATH --profile telegram up -d telegram_worker"
