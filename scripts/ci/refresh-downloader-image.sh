#!/bin/bash
# scripts/ci/refresh-downloader-image.sh
#
# Rebuilds and pushes the downloader image from the *already released* commit on
# master, so production picks up a newer yt-dlp without waiting for a release.
# The yt-dlp it installs is the one pinned on develop, where Renovate lands every
# bump (see YT_DLP_VERSION below); nothing is taken from PyPI unpinned any more.
#
# Why this exists: yt-dlp chases a moving target. When SoundCloud or YouTube
# changes something, the fix lands in a yt-dlp release within days, but our images
# are only ever built by release:build-images on a release/* branch. Between two
# releases the downloader therefore runs a yt-dlp that is as old as the last one -
# which is how "downloads just stopped working" happens without anything in this
# repo having changed.
#
# What it deliberately does NOT do:
#   - It does not run the deploy. It republishes an image; Watchtower, which
#     already runs on the production host, pulls it.
#   - It does not re-push the ":${VERSION}" tag. That tag names a release and has
#     to keep meaning the artifact that release shipped. Only ":latest" (what
#     docker-compose.yml pulls) and a dated tag are pushed, so there is still a
#     record of which refresh produced which image.
#   - It only touches the muma-base family: the base itself and every image built
#     FROM it (downloader, telegram, importer). music-manager, lms and tools have
#     their own FROM and are only ever built by a release.
#
# Why the whole family and not just the downloader: the base is rebuilt here with
# --no-cache, so it picks up that day's Debian-Security packages. An image built
# FROM it keeps whatever its own last build inherited, which is the release build.
# Rebuilding only the base therefore *creates* the gap -- on 2026-09-07 the audit
# found CVE-2026-33164 (libde265) in muma-telegram and muma-importer while the base
# they are built on had been clean since that night's refresh. The two derived
# images are a handful of COPY layers, so rebuilding them costs seconds.
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
    echo "Error: DOCKERHUB_USERNAME / DOCKERHUB_TOKEN CI/CD variables are not set. See docs/self-hosting.md."
    exit 1
fi

if [ -z "${PROD_ENV_FILE}" ]; then
    echo "Error: PROD_ENV_FILE CI/CD variable is not set. See docs/self-hosting.md."
    exit 1
fi

# shellcheck source=scripts/ci/docker-hub-session.sh
. "$SCRIPT_DIR/docker-hub-session.sh"

# Same materialization release:build-images does: the image names production
# pulls live in the prod .env, and jobs do not share a filesystem. Written to a
# private temp directory rather than the checkout, which is the build context
# of every image below and outlives the job on the shell-executor runner.
ENV_DIR="$(mktemp -d)"
chmod 700 "$ENV_DIR"
ROOT_ENV_FILE="$ENV_DIR/music-management.env"

# cleanup_on_exit: end the Docker Hub session and remove the env file.
cleanup_on_exit() {
    docker_hub_logout
    rm -rf "$ENV_DIR"
}
trap cleanup_on_exit EXIT

(
    umask 077
    if [ -f "${PROD_ENV_FILE}" ]; then
        cp "${PROD_ENV_FILE}" "$ROOT_ENV_FILE"
    else
        printf '%s\n' "${PROD_ENV_FILE}" > "$ROOT_ENV_FILE"
    fi
)

docker_hub_login

set -a
# shellcheck disable=SC1090,SC1091 # a per-run env file, path known only at runtime
source "$ROOT_ENV_FILE"
set +a
DOCKER_USER="${DOCKER_USER:-$DOCKERHUB_USERNAME}"
IMAGE_BASE="${IMAGE_BASE:-muma-base}"
IMAGE_DOWNLOADER="${IMAGE_DOWNLOADER:-muma-downloader}"
IMAGE_TELEGRAM="${IMAGE_TELEGRAM:-muma-telegram}"
IMAGE_IMPORTER="${IMAGE_IMPORTER:-muma-importer}"

REFRESH_TAG="refresh-$(date -u +%Y%m%d)"

# Which yt-dlp to build. yt-dlp is pinned (requirements.txt, docker/Dockerfile.downloader)
# and Renovate lands every bump on develop, usually within hours of the release. This job
# builds master, which is a release behind develop, so building master's own pin would
# ship nothing new between releases -- the one thing this job exists for. It takes
# develop's pin instead: a version that has passed a develop pipeline, rather than
# whatever PyPI serves today. If develop cannot be read, master's pin is used and the
# log says so; the OS-package half of the refresh is still worth doing.
# pinned_yt_dlp: print the yt-dlp version pinned in a requirements.txt read from stdin.
pinned_yt_dlp() {
    sed -n 's/^yt-dlp==\([^[:space:]#]*\).*/\1/p' | head -n 1
}
YT_DLP_VERSION=""
if git fetch --quiet origin develop 2>/dev/null; then
    YT_DLP_VERSION="$(git show FETCH_HEAD:requirements.txt | pinned_yt_dlp)"
fi
if [ -z "$YT_DLP_VERSION" ]; then
    YT_DLP_VERSION="$(pinned_yt_dlp < requirements.txt)"
    echo "Warning: could not read develop's yt-dlp pin, building master's (${YT_DLP_VERSION})."
else
    echo "--- yt-dlp ${YT_DLP_VERSION}, as pinned on develop ---"
fi
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
    --build-arg YT_DLP_VERSION="${YT_DLP_VERSION}" \
    -t "${DOCKER_USER}/${IMAGE_DOWNLOADER}:latest" \
    -t "${DOCKER_USER}/${IMAGE_DOWNLOADER}:${REFRESH_TAG}" \
    -f docker/Dockerfile.downloader .

docker push "${DOCKER_USER}/${IMAGE_DOWNLOADER}:latest"
docker push "${DOCKER_USER}/${IMAGE_DOWNLOADER}:${REFRESH_TAG}"

# The two remaining images built FROM muma-base. They add a pip install and some
# COPY layers, so what they are really here for is the base's OS packages -- see
# the header. VERSION=latest points their FROM at the base built a few lines up.
echo "--- Building ${DOCKER_USER}/${IMAGE_TELEGRAM} ---"
docker build --no-cache \
    --build-arg DOCKER_USER="${DOCKER_USER}" \
    --build-arg VERSION="latest" \
    -t "${DOCKER_USER}/${IMAGE_TELEGRAM}:latest" \
    -t "${DOCKER_USER}/${IMAGE_TELEGRAM}:${REFRESH_TAG}" \
    -f docker/Dockerfile.telegram .

docker push "${DOCKER_USER}/${IMAGE_TELEGRAM}:latest"
docker push "${DOCKER_USER}/${IMAGE_TELEGRAM}:${REFRESH_TAG}"

echo "--- Building ${DOCKER_USER}/${IMAGE_IMPORTER} ---"
docker build --no-cache \
    --build-arg DOCKER_USER="${DOCKER_USER}" \
    --build-arg VERSION="latest" \
    -t "${DOCKER_USER}/${IMAGE_IMPORTER}:latest" \
    -t "${DOCKER_USER}/${IMAGE_IMPORTER}:${REFRESH_TAG}" \
    -f docker/Dockerfile.importer .

docker push "${DOCKER_USER}/${IMAGE_IMPORTER}:latest"
docker push "${DOCKER_USER}/${IMAGE_IMPORTER}:${REFRESH_TAG}"

echo "--- Installed yt-dlp ---"
docker run --rm "${DOCKER_USER}/${IMAGE_DOWNLOADER}:${REFRESH_TAG}" yt-dlp --version

echo "--- Refresh complete. Watchtower will pull :latest on the production host. ---"
