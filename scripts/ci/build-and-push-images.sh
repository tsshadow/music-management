#!/bin/bash
# scripts/ci/build-and-push-images.sh
#
# Builds and pushes ALL Docker images that production actually pulls, from CI,
# on a release/* branch, *before* deploy:prod runs. This closes the gap that
# caused deploy:prod to only ever "docker compose pull" whatever image was
# last pushed manually (often stale/old) - see docs/release-management.md and
# CHANGELOG.md 0.0.2 for the full story.
#
# NOTE: this originally only covered music-manager/lms (bullets 1-2 below).
# See docs/bug-reports/007-telegram-session-schema-mismatch.md: a fix to the
# telegram worker's Dockerfile/dependencies went through a full green
# release/deploy:prod pipeline but never actually reached production, because
# nothing in CI ever rebuilt+pushed the muma-telegram (or muma-downloader/
# muma-importer/muma-tools/muma-base) images - "docker compose pull" just kept
# re-pulling the same old manually-pushed ":latest" tag. Bullets 3-6 close
# that gap for every image docker/docker-compose.yml actually references.
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
#   3. muma-base (docker/Dockerfile.base) - common base image for 4-6 below.
#      Not referenced directly by docker-compose.yml, but must be rebuilt
#      first and pushed so the FROM ${DOCKER_USER}/muma-base:latest in the
#      Dockerfiles below actually picks up the current requirements.txt/code.
#   4. muma-downloader (docker/Dockerfile.downloader) -> "${DOCKER_USER}/${IMAGE_DOWNLOADER}"
#      (soundcloud/youtube/generic downloader workers).
#   5. muma-telegram (docker/Dockerfile.telegram) -> "${DOCKER_USER}/${IMAGE_TELEGRAM}"
#      (telegram_worker).
#   6. muma-importer (docker/Dockerfile.importer) -> "${DOCKER_USER}/${IMAGE_IMPORTER}"
#      (importer_worker).
#   7. muma-tools (docker/Dockerfile.tools) -> "${DOCKER_USER}/${IMAGE_TOOLS}"
#      (soundcloud-fetcher, process_genres tools).
#
# Required CI/CD variables (see docs/deployment.md):
#   - DOCKERHUB_USERNAME, DOCKERHUB_TOKEN: Docker Hub login used to push.
#   - PROD_ENV_FILE, PROD_ENV_FILE_LMS: same file-type variables deploy:prod
#     already uses, needed here too so IMAGE_CORE/IMAGE_NAME/IMAGE_* resolve
#     to the exact same values docker-compose.yml will pull on the
#     production host.
#
# This job is gated in .gitlab-ci.yml on DOCKERHUB_USERNAME/DOCKERHUB_TOKEN
# being present, but since it runs before deploy:prod (same "release" stage,
# earlier than the "deploy" stage), a missing/failed build here blocks
# deploy:prod from ever running against a stale image.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# PUSH_IMAGES=false builds every image and pushes none of it.
#
# That mode exists for the docker:build-images job, which runs on merge requests
# that touch a Dockerfile. Until it existed, a Dockerfile-only change ran no job
# that built anything: five of the seven images below (base, downloader,
# telegram, importer, tools) are not in docker/compose.test.yml either, so the
# first time anything compiled them was release:build-images on a release
# branch - the worst possible place to discover a broken build.
#
# It deliberately reuses this script rather than a second, simpler one: two
# build definitions for the same Dockerfiles is how the merge-request build
# drifts from the release build and stops proving anything.
PUSH_IMAGES="${PUSH_IMAGES:-true}"

docker_push() {
    if [ "$PUSH_IMAGES" != "true" ]; then
        echo "    (PUSH_IMAGES=false, not pushing $1)"
        return 0
    fi
    docker push "$1"
}

if [ "$PUSH_IMAGES" = "true" ] && { [ -z "$DOCKERHUB_USERNAME" ] || [ -z "$DOCKERHUB_TOKEN" ]; }; then
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

if [ "$PUSH_IMAGES" = "true" ]; then
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
else
    # No push means no production secrets: a merge-request pipeline must not
    # need PROD_ENV_FILE at all. The image *names* are the only thing those
    # files contribute to a build, and a build proves the same thing under a
    # throwaway name. Written rather than skipped because the script sources
    # both files under `set -e`.
    #
    # Only ever written when absent. In CI they always are (.env is gitignored,
    # so a fresh checkout has none), but this script is runnable by hand, and
    # overwriting a developer's real .env with placeholders would be a nasty
    # way to find that out.
    echo "--- PUSH_IMAGES=false: building under local names, no Docker Hub login ---"
    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        printf 'DOCKER_USER=muma-ci\nIMAGE_CORE=music-manager\n' > "$PROJECT_ROOT/.env"
    fi
    if [ ! -f "$PROJECT_ROOT/services/music-management-server/.env" ]; then
        printf 'IMAGE_NAME=muma-ci/lms\n' > "$PROJECT_ROOT/services/music-management-server/.env"
    fi
fi

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
docker_push "${DOCKER_USER}/${IMAGE_CORE}:latest"
docker_push "${DOCKER_USER}/${IMAGE_CORE}:${VERSION}"

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
    --build-arg VITE_GOOGLE_CLIENT_ID="${VITE_GOOGLE_CLIENT_ID}" \
    -t "${IMAGE_NAME}:latest" \
    -t "${IMAGE_NAME}:stable" \
    -t "${IMAGE_NAME}:${LMS_VERSION}" \
    -f services/music-management-server/Dockerfile-release .

echo "--- Pushing lms image ---"
docker_push "${IMAGE_NAME}:latest"
docker_push "${IMAGE_NAME}:stable"
docker_push "${IMAGE_NAME}:${LMS_VERSION}"

# 3. Build + push muma-base ----------------------------------------------------
# (re-source root .env: sourcing PROD_ENV_FILE_LMS above may have shadowed
# some of its variables since both files are sourced into the same shell)
# shellcheck disable=SC1091
set -a; source "$PROJECT_ROOT/.env"; set +a
DOCKER_USER="${DOCKER_USER:-$DOCKERHUB_USERNAME}"
IMAGE_BASE="${IMAGE_BASE:-muma-base}"
IMAGE_DOWNLOADER="${IMAGE_DOWNLOADER:-muma-downloader}"
IMAGE_TELEGRAM="${IMAGE_TELEGRAM:-muma-telegram}"
IMAGE_IMPORTER="${IMAGE_IMPORTER:-muma-importer}"
IMAGE_TOOLS="${IMAGE_TOOLS:-muma-tools}"

echo "--- Building muma-base image (${DOCKER_USER}/${IMAGE_BASE}:${VERSION}) ---"
docker build \
    -t "${DOCKER_USER}/${IMAGE_BASE}:latest" \
    -t "${DOCKER_USER}/${IMAGE_BASE}:${VERSION}" \
    -f docker/Dockerfile.base .

echo "--- Pushing muma-base image ---"
docker_push "${DOCKER_USER}/${IMAGE_BASE}:latest"
docker_push "${DOCKER_USER}/${IMAGE_BASE}:${VERSION}"

# 4. Build + push muma-downloader ----------------------------------------------
echo "--- Building muma-downloader image (${DOCKER_USER}/${IMAGE_DOWNLOADER}:${VERSION}) ---"
docker build \
    --build-arg DOCKER_USER="${DOCKER_USER}" \
    --build-arg VERSION="${VERSION}" \
    -t "${DOCKER_USER}/${IMAGE_DOWNLOADER}:latest" \
    -t "${DOCKER_USER}/${IMAGE_DOWNLOADER}:${VERSION}" \
    -f docker/Dockerfile.downloader .

echo "--- Pushing muma-downloader image ---"
docker_push "${DOCKER_USER}/${IMAGE_DOWNLOADER}:latest"
docker_push "${DOCKER_USER}/${IMAGE_DOWNLOADER}:${VERSION}"

# 5. Build + push muma-telegram -------------------------------------------------
echo "--- Building muma-telegram image (${DOCKER_USER}/${IMAGE_TELEGRAM}:${VERSION}) ---"
docker build \
    --build-arg DOCKER_USER="${DOCKER_USER}" \
    --build-arg VERSION="${VERSION}" \
    -t "${DOCKER_USER}/${IMAGE_TELEGRAM}:latest" \
    -t "${DOCKER_USER}/${IMAGE_TELEGRAM}:${VERSION}" \
    -f docker/Dockerfile.telegram .

echo "--- Pushing muma-telegram image ---"
docker_push "${DOCKER_USER}/${IMAGE_TELEGRAM}:latest"
docker_push "${DOCKER_USER}/${IMAGE_TELEGRAM}:${VERSION}"

# 6. Build + push muma-importer -------------------------------------------------
echo "--- Building muma-importer image (${DOCKER_USER}/${IMAGE_IMPORTER}:${VERSION}) ---"
docker build \
    --build-arg DOCKER_USER="${DOCKER_USER}" \
    --build-arg VERSION="${VERSION}" \
    -t "${DOCKER_USER}/${IMAGE_IMPORTER}:latest" \
    -t "${DOCKER_USER}/${IMAGE_IMPORTER}:${VERSION}" \
    -f docker/Dockerfile.importer .

echo "--- Pushing muma-importer image ---"
docker_push "${DOCKER_USER}/${IMAGE_IMPORTER}:latest"
docker_push "${DOCKER_USER}/${IMAGE_IMPORTER}:${VERSION}"

# 7. Build + push muma-tools ----------------------------------------------------
echo "--- Building muma-tools image (${DOCKER_USER}/${IMAGE_TOOLS}:${VERSION}) ---"
docker build \
    -t "${DOCKER_USER}/${IMAGE_TOOLS}:latest" \
    -t "${DOCKER_USER}/${IMAGE_TOOLS}:${VERSION}" \
    -f docker/Dockerfile.tools .

echo "--- Pushing muma-tools image ---"
docker_push "${DOCKER_USER}/${IMAGE_TOOLS}:latest"
docker_push "${DOCKER_USER}/${IMAGE_TOOLS}:${VERSION}"

echo "--- build-and-push-images.sh completed: music-manager, lms, and all background worker images (base/downloader/telegram/importer/tools) are now up to date on Docker Hub ---"
