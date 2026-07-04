#!/bin/bash
set -e

# Update package list
echo "Updating package list..."
sudo apt-get update

# Install Docker if not present
if ! command -v docker &> /dev/null
then
    echo "Docker not found, installing..."
    sudo apt-get install -y docker.io
    sudo systemctl start docker
    sudo systemctl enable docker
else
    echo "Docker is already installed."
fi

# Install Docker Compose if not present
if ! command -v docker-compose &> /dev/null
then
    echo "Docker Compose not found, installing..."
    sudo apt-get install -y docker-compose
else
    echo "Docker Compose is already installed."
fi

# Add current user to docker group
if ! getent group docker | grep -q "\b$USER\b"; then
    echo "Adding user $USER to docker group..."
    sudo usermod -aG docker "$USER"
    echo "User $USER added to docker group."
else
    echo "User $USER is already in the docker group."
fi

# Install sshpass if not present
if ! command -v sshpass &> /dev/null
then
    echo "sshpass not found, installing..."
    sudo apt-get install -y sshpass
else
    echo "sshpass is already installed."
fi

echo "Requirements installation completed."

# Apply group membership to the current session
if ! groups | grep -q "\bdocker\b"; then
    echo "Applying docker group membership to the current session via 'newgrp docker'..."
    newgrp docker
fi
