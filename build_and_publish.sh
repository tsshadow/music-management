#!/bin/bash
set -e

# Change to the directory where the script is located
cd "$(dirname "$0")"

IMAGE_NAME="muma/lms"
TAG="alpha"

# Remote server configuration
REMOTE_HOST="192.0.2.27"
REMOTE_USER="root"
# REMOTE_PASS="your_password_here" (Set this env var or enter it when prompted if not using sshpass)
CONTAINER_NAME="lms-alpha"

echo "Building Docker image ${IMAGE_NAME}:${TAG}..."
docker build -t "${IMAGE_NAME}:${TAG}" -f Dockerfile-release .

echo "Pushing Docker image ${IMAGE_NAME}:${TAG}..."
docker push "${IMAGE_NAME}:${TAG}"

echo "Updating remote server ${REMOTE_HOST}..."
if [ -z "${REMOTE_PASS}" ]; then
    echo "REMOTE_PASS environment variable not set. Please enter password if prompted."
    ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} "
        docker pull ${IMAGE_NAME}:${TAG}
        docker stop ${CONTAINER_NAME} || true
        docker rm ${CONTAINER_NAME} || true
        docker run -d --name ${CONTAINER_NAME} --restart unless-stopped -p 5082:5082 -v /var/lms:/var/lms -v /music:/music ${IMAGE_NAME}:${TAG}
    "
elif command -v sshpass >/dev/null 2>&1; then
    sshpass -p "${REMOTE_PASS}" ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} "
        docker pull ${IMAGE_NAME}:${TAG}
        docker stop ${CONTAINER_NAME} || true
        docker rm ${CONTAINER_NAME} || true
        docker run -d --name ${CONTAINER_NAME} --restart unless-stopped -p 5082:5082 -v /var/lms:/var/lms -v /music:/music ${IMAGE_NAME}:${TAG}
    "
else
    echo "Error: sshpass not found. Please install it to enable automatic deployment."
    exit 1
fi

echo "Build, publish and deploy completed successfully!"
