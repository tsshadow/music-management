#!/bin/bash
# scripts/ci/refresh-downloader-image.sh
#
# Rebuilds and pushes the downloader image from the *already released* commit on
# master, so production picks up a newer yt-dlp without waiting for a release.
#
# Why this exists: yt-dlp chases a moving target. When SoundCloud or YouTube
# changes something, the fix lands in a yt-dlp release within days, but our images
# are only ever built by release:build-images on a release/* branch. Between two
# releases the downloader therefore runs a yt-dlp that is as old as the last one -
# which is how "downloads just stopped working" happens without anything in this
# repo having changed.
#
# What it deliberately does NOT do:
#   - It does not run deploy:prod. It republishes an image; Watchtower, which
#     already runs on the production host, pulls it.
#   - It does not re-push the ":${VERSION}" tag. That tag names a release and has
#     to keep meaning the artifact that release shipped. Only ":latest" (what
#     docker-compose.yml pulls) and a dated tag are pushed, so there is still a
#     record of which refresh produced which image.
#   - It only touches muma-base and muma-downloader. Nothing else in the stack
#     depends on a dependency that moves this fast.
#
# See docs/bug-reports/016-stale-release-branch-clobbered-latest-deploy.md for why
# "which commit is :latest built from" is treated carefully here: this script is
# gated in .gitlab-ci.yml on running from master, the branch whose content
# production is already running.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

if [ -z "$DOCKERHUB_USERNAME" ] || [ -z "$DOCKERHUB_TOKEN" ]; then
    echo "Error: DOCKERHUB_USERNAME / DOCKERHUB_TOKEN CI/CD variables are not set. See docs/deployment.md."
    exit 1
fi

if [ -z "${PROD_ENV_FILE}" ]; then
    echo "Error: PROD_ENV_FILE CI/CD variable is not set. See docs/deployment.md."
    exit 1
fi

# Same materialization release:build-images does: the image names production
# pulls live in the prod .env, and jobs do not share a filesystem.
if [ -f "${PROD_ENV_FILE}" ]; then
    cp "${PROD_ENV_FILE}" "$PROJECT_ROOT/.env"
else
    printf '%s\n' "${PROD_ENV_FILE}" > "$PROJECT_ROOT/.env"
fi

echo "--- Logging in to Docker Hub as ${DOCKERHUB_USERNAME} ---"
echo "${DOCKERHUB_TOKEN}" | docker login --username "${DOCKERHUB_USERNAME}" --password-stdin

# shellcheck disable=SC1091
set -a; source "$PROJECT_ROOT/.env"; set +a
DOCKER_USER="${DOCKER_USER:-$DOCKERHUB_USERNAME}"
IMAGE_BASE="${IMAGE_BASE:-muma-base}"
IMAGE_DOWNLOADER="${IMAGE_DOWNLOADER:-muma-downloader}"

REFRESH_TAG="refresh-$(date -u +%Y%m%d)"
echo "--- Refreshing from $(git rev-parse --short HEAD) on ${CI_COMMIT_BRANCH:-unknown}, tagging ${REFRESH_TAG} ---"

# --no-cache on the dependency layers is the whole point: a cached
# "pip install yt-dlp" would reinstall the very version we are trying to leave.
echo "--- Building ${DOCKER_USER}/${IMAGE_BASE} ---"
docker build --no-cache \
    -t "${DOCKER_USER}/${IMAGE_BASE}:latest" \
    -t "${DOCKER_USER}/${IMAGE_BASE}:${REFRESH_TAG}" \
    -f docker/Dockerfile.base .

docker push "${DOCKER_USER}/${IMAGE_BASE}:latest"
docker push "${DOCKER_USER}/${IMAGE_BASE}:${REFRESH_TAG}"

echo "--- Building ${DOCKER_USER}/${IMAGE_DOWNLOADER} ---"
docker build --no-cache \
    --build-arg DOCKER_USER="${DOCKER_USER}" \
    --build-arg VERSION="latest" \
    -t "${DOCKER_USER}/${IMAGE_DOWNLOADER}:latest" \
    -t "${DOCKER_USER}/${IMAGE_DOWNLOADER}:${REFRESH_TAG}" \
    -f docker/Dockerfile.downloader .

docker push "${DOCKER_USER}/${IMAGE_DOWNLOADER}:latest"
docker push "${DOCKER_USER}/${IMAGE_DOWNLOADER}:${REFRESH_TAG}"

echo "--- Installed yt-dlp ---"
docker run --rm "${DOCKER_USER}/${IMAGE_DOWNLOADER}:${REFRESH_TAG}" yt-dlp --version

echo "--- Refresh complete. Watchtower will pull :latest on the production host. ---"
