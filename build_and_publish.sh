#!/bin/bash
set -e

cd "$(dirname "$0")"
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Ensure variables are set
IMAGE_NAME="${IMAGE_NAME:-muma/lms}"
TAG="${TAG:-alpha}"
REMOTE_HOST="${REMOTE_HOST}"
REMOTE_USER="${REMOTE_USER}"
REMOTE_PASS="${REMOTE_PASS}"
SERVICE_NAME="${SERVICE_NAME:-lms-alpha}"

if [ -z "${REMOTE_HOST}" ] || [ -z "${REMOTE_USER}" ]; then
    echo "Error: REMOTE_HOST and REMOTE_USER must be set in .env"
    exit 1
fi

echo "Building Docker image ${IMAGE_NAME}:${TAG}..."
docker build -t "${IMAGE_NAME}:${TAG}" -f Dockerfile-release .

echo "Pushing Docker image ${IMAGE_NAME}:${TAG}..."
docker push "${IMAGE_NAME}:${TAG}"

REMOTE_COMMAND="
set -e
docker pull ${IMAGE_NAME}:${TAG}
docker stop ${SERVICE_NAME} || true
docker rm ${SERVICE_NAME} || true
docker run -d --name ${SERVICE_NAME} \
    --restart unless-stopped \
    -p 8080:5082 \
    -v /music:/music \
    -v /docker/${SERVICE_NAME}/usr/local/etc:/usr/local/etc \
    -v /docker/${SERVICE_NAME}/var/lms:/var/lms \
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
