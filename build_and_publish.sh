#!/bin/bash
set -e

cd "$(dirname "$0")"
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

IMAGE_NAME="muma/lms"
TAG="alpha"

REMOTE_HOST="192.0.2.27"
REMOTE_USER="root"
REMOTE_PASS="${REMOTE_PASS:-}"
STACK_DIR="/data/compose/24"
SERVICE_NAME="alpha"

echo "Building Docker image ${IMAGE_NAME}:${TAG}..."
docker build -t "${IMAGE_NAME}:${TAG}" -f Dockerfile-release .

echo "Pushing Docker image ${IMAGE_NAME}:${TAG}..."
docker push "${IMAGE_NAME}:${TAG}"

REMOTE_COMMAND="
set -e
docker pull ${IMAGE_NAME}:${TAG}
docker stop lms_alpha || true
docker rm lms_alpha || true
docker run -d --name lms_alpha \
    --restart unless-stopped \
    -p 8080:5082 \
    -v /music:/music \
    -v /docker/lms-alpha/usr/local/etc:/usr/local/etc \
    -v /docker/lms-alpha/var/lms:/var/lms \
    --user 0:0 \
    ${IMAGE_NAME}:${TAG}
"

echo "Updating remote server ${REMOTE_HOST}..."

if [ -z "${REMOTE_PASS}" ]; then
    echo "REMOTE_PASS not set. SSH may ask for password."
    ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" "${REMOTE_COMMAND}"
elif command -v sshpass >/dev/null 2>&1; then
    sshpass -p "${REMOTE_PASS}" ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" "${REMOTE_COMMAND}"
else
    echo "Error: sshpass not found. Install it or unset REMOTE_PASS and enter password manually."
    exit 1
fi

echo "Build, publish and deploy completed successfully!"
