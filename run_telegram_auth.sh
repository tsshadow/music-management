#!/bin/bash
set -e

# Telegram Authentication Helper Script
# This script helps with the one-time interactive authentication for Telegram.

# Default channel if none provided
CHANNEL=${1:-"Hard Dance Events"}

# Check if we are in the project root
if [ ! -f "work-context/docker-compose.yml" ]; then
    echo "Error: work-context/docker-compose.yml not found."
    echo "Please run this script from the music-management project root."
    exit 1
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

$DOCKER_CMD -f work-context/docker-compose.yml run --rm -it telegram_worker python services/downloader/downloader_service.py --step telegram --account "$CHANNEL"

echo ""
echo "--- Authentication Complete ---"
echo "You can now start the worker in the background using:"
echo "$DOCKER_CMD -f work-context/docker-compose.yml up -d telegram_worker"
