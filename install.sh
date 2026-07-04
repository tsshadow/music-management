#!/bin/bash
# Installation script for LMS build dependencies (Docker)
set -e

echo "--- Installing dependencies for Docker build ---"
sudo apt-get update
sudo apt-get install -y docker.io sshpass

# Add current user to docker group
if ! groups $USER | grep -q "\bdocker\b"; then
    echo "Adding $USER to docker group..."
    sudo usermod -aG docker $USER
    echo "User added to docker group. You may need to restart your session or run 'newgrp docker'."
fi

# Apply group membership to the current session

if ! groups | grep -q "\bdocker\b"; then
    echo "Applying docker group membership to the current session via 'newgrp docker'..."
    newgrp docker
fi

if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo ".env file created from .env.example. Please update it with your actual settings."
    else
        echo "Warning: .env.example not found, skipping .env creation."
    fi
fi

echo "--- Dependencies installed ---"
echo "You can now run ./build_and_publish.sh to build and publish the Docker image."
