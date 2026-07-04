#!/bin/bash
# Installation script for LMS build dependencies (Docker)
set -e

echo "--- Installing dependencies for Docker build ---"
sudo apt-get update
sudo apt-get install -y docker.io sshpass
# Apply group membership to the current session

if ! groups | grep -q "\bdocker\b"; then
    echo "Applying docker group membership to the current session via 'newgrp docker'..."
    newgrp docker
fi

if [ ! -f .env ]; then
    echo "Creating .env file..."
    cat <<EOF > .env
IMAGE_NAME=muma/lms
TAG=alpha
REMOTE_HOST=192.0.2.27
REMOTE_USER=root
REMOTE_PASS=redacted
STACK_DIR=/data/compose/24
SERVICE_NAME=lms-alpha
EOF
    echo ".env file created. Please update REMOTE_PASS in .env."
fi

echo "--- Dependencies installed ---"
echo "You can now run ./build_and_publish.sh to build and publish the Docker image."
