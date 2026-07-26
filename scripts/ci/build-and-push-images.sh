#!/bin/bash
# scripts/ci/build-and-push-images.sh
#
# Builds and pushes the two Docker images that production actually pulls, from
# CI, on a release/* branch, *before* deploy:prod runs. This closes the gap
# that caused deploy:prod to only ever "docker compose pull" whatever image
# was last pushed manually (often stale/old) - see docs/release-management.md
# and CHANGELOG.md 0.0.2 for the full story.
#
#   1. music-manager  (docker/Dockerfile.music-manager, build context: repo root)
#      -> pushed as "${DOCKER_USER}/${IMAGE_CORE}:latest" and ":${VERSION}"
#         (matches docker/docker-compose.yml's `image: ${DOCKER_USER}/${IMAGE_CORE}:latest`).
#   2. lms / music-management-server (services/music-management-server/Dockerfile-release,
#      build context: repo root)
#      -> pushed as "${IMAGE_NAME}:latest", ":stable" and ":${LMS_VERSION}"
#         (matches services/music-management-server/docker-compose.yml's
#         `image: ${IMAGE_NAME}:${LMS_TAG}` - both "latest" and "stable" are
#         pushed so this works regardless of which one LMS_TAG is set to).
#
# Required CI/CD variables (see docs/deployment.md):
#   - DOCKERHUB_USERNAME, DOCKERHUB_TOKEN: Docker Hub login used to push.
#   - PROD_ENV_FILE, PROD_ENV_FILE_LMS: same file-type variables deploy:prod
#     already uses, needed here too so IMAGE_CORE/IMAGE_NAME resolve to the
#     exact same values docker-compose.yml will pull on the production host.
#
# This job is gated in .gitlab-ci.yml on DOCKERHUB_USERNAME/DOCKERHUB_TOKEN
# being present, but since it runs before deploy:prod (same "release" stage,
# earlier than the "deploy" stage), a missing/failed build here blocks
# deploy:prod from ever running against a stale image.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

if [ -z "$DOCKERHUB_USERNAME" ] || [ -z "$DOCKERHUB_TOKEN" ]; then
    echo "Error: DOCKERHUB_USERNAME / DOCKERHUB_TOKEN CI/CD variables are not set. See docs/deployment.md."
    exit 1
fi

# Materialize the .env files from the same file-type CI/CD variables
# deploy:prod uses, so IMAGE_CORE/DOCKER_USER/IMAGE_NAME/LMS_TAG match exactly
# what production will pull (jobs don't share a filesystem, so this has to be
# redone here rather than relying on what ci-deploy.sh writes in a later job).
write_env_file() {
    local var_value="$1"
    local dest="$2"
    if [ -f "${var_value}" ]; then
        cp "${var_value}" "$dest"
    else
        printf '%s\n' "${var_value}" > "$dest"
    fi
}

if [ -z "${PROD_ENV_FILE}" ]; then
    echo "Error: PROD_ENV_FILE CI/CD variable is not set. See docs/deployment.md."
    exit 1
fi
write_env_file "${PROD_ENV_FILE}" "$PROJECT_ROOT/.env"

if [ -z "${PROD_ENV_FILE_LMS}" ]; then
    echo "Error: PROD_ENV_FILE_LMS CI/CD variable is not set. See docs/deployment.md."
    exit 1
fi
write_env_file "${PROD_ENV_FILE_LMS}" "$PROJECT_ROOT/services/music-management-server/.env"

echo "--- Logging in to Docker Hub as ${DOCKERHUB_USERNAME} ---"
echo "${DOCKERHUB_TOKEN}" | docker login --username "${DOCKERHUB_USERNAME}" --password-stdin

VERSION=$(cat VERSION 2>/dev/null || echo "latest")

# 1. Build + push music-manager -----------------------------------------------
# shellcheck disable=SC1091
set -a; source "$PROJECT_ROOT/.env"; set +a
DOCKER_USER="${DOCKER_USER:-$DOCKERHUB_USERNAME}"
IMAGE_CORE="${IMAGE_CORE:-music-manager}"

echo "--- Building music-manager image (${DOCKER_USER}/${IMAGE_CORE}:${VERSION}) ---"
docker build \
    --build-arg DOCKER_USER="${DOCKER_USER}" \
    --build-arg VERSION="${VERSION}" \
    -t "${DOCKER_USER}/${IMAGE_CORE}:latest" \
    -t "${DOCKER_USER}/${IMAGE_CORE}:${VERSION}" \
    -f docker/Dockerfile.music-manager .

echo "--- Pushing music-manager image ---"
docker push "${DOCKER_USER}/${IMAGE_CORE}:latest"
docker push "${DOCKER_USER}/${IMAGE_CORE}:${VERSION}"

# 2. Build + push lms (music-management-server) -------------------------------
# shellcheck disable=SC1091
set -a; source "$PROJECT_ROOT/services/music-management-server/.env"; set +a
if [ -z "${IMAGE_NAME}" ]; then
    echo "Error: IMAGE_NAME is not set in PROD_ENV_FILE_LMS."
    exit 1
fi
LMS_VERSION=$(grep "project(lms VERSION" services/music-management-server/CMakeLists.txt | sed 's/.*VERSION \(.*\))/\1/')

echo "--- Building lms image (${IMAGE_NAME}:${LMS_VERSION}) ---"
docker build \
    -t "${IMAGE_NAME}:latest" \
    -t "${IMAGE_NAME}:stable" \
    -t "${IMAGE_NAME}:${LMS_VERSION}" \
    -f services/music-management-server/Dockerfile-release .

echo "--- Pushing lms image ---"
docker push "${IMAGE_NAME}:latest"
docker push "${IMAGE_NAME}:stable"
docker push "${IMAGE_NAME}:${LMS_VERSION}"

echo "--- build-and-push-images.sh completed: music-manager and lms images are now up to date on Docker Hub ---"
