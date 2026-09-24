#!/bin/bash
# scripts/ci/promote-release-images.sh
#
# Moves this release's images from ":${VERSION}" to the tags production pulls:
# ":latest" for every image, and ":stable" as well for lms. Run by muma:deploy,
# through scripts/deploy.sh's DEPLOY_PRE_UP_HOOK, after the pre-deploy backup
# and the migrations have succeeded and before any container is recreated.
#
# Why here and not in release:build-images: Watchtower on the production host
# pulls ":latest" of the downloader family whenever it changes. When the build
# job pushed ":latest", Watchtower could start a release's code minutes before
# muma:deploy had applied that release's migrations -- and it did so even when
# muma:deploy never ran at all (a red mobile job skips it). The build job now
# pushes ":${VERSION}" and ":rc" only; this script is the one place ":latest"
# moves. See docs/bug-reports/050-deploy-starts-new-code-before-migrations.md.
#
# The copy is registry-side (`docker buildx imagetools create`) when buildx is
# available, so the digest production pulls is exactly the one the build job
# pushed; otherwise pull, tag and push, which yields the same image id.
#
# Environment:
#   DOCKERHUB_USERNAME, DOCKERHUB_TOKEN  push credentials (throwaway DOCKER_CONFIG)
#   PROMOTE_ENV_FILE       the music-management .env (DOCKER_USER, IMAGE_*)
#   PROMOTE_LMS_ENV_FILE   the lms .env (IMAGE_NAME)
# The version is always the VERSION file, as in build-and-push-images.sh -- never
# a VERSION that an env file may have exported into the environment.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# shellcheck source=scripts/lib/dotenv.sh
. "$PROJECT_ROOT/scripts/lib/dotenv.sh"
# shellcheck source=scripts/ci/docker-hub-session.sh
. "$SCRIPT_DIR/docker-hub-session.sh"
trap docker_hub_logout EXIT

RELEASE_VERSION="$(tr -d '[:space:]' < "$PROJECT_ROOT/VERSION")"
if [ -z "$RELEASE_VERSION" ]; then
    echo "Error: no VERSION to promote."
    exit 1
fi

if [ -z "$DOCKERHUB_USERNAME" ] || [ -z "$DOCKERHUB_TOKEN" ]; then
    echo "Error: DOCKERHUB_USERNAME / DOCKERHUB_TOKEN are not set; cannot move :latest to ${RELEASE_VERSION}."
    exit 1
fi
for env_file in "${PROMOTE_ENV_FILE:-}" "${PROMOTE_LMS_ENV_FILE:-}"; do
    if [ ! -f "$env_file" ]; then
        echo "Error: PROMOTE_ENV_FILE and PROMOTE_LMS_ENV_FILE must name the two stacks' env files."
        exit 1
    fi
done

# The image names, resolved exactly the way build-and-push-images.sh resolves
# them, so the tag that moves is the tag that was built.
dotenv_load "$PROMOTE_ENV_FILE"
DOCKER_USER="${DOCKER_USER:-$DOCKERHUB_USERNAME}"
IMAGE_CORE="${IMAGE_CORE:-music-manager}"
IMAGE_BASE="${IMAGE_BASE:-muma-base}"
IMAGE_DOWNLOADER="${IMAGE_DOWNLOADER:-muma-downloader}"
IMAGE_TELEGRAM="${IMAGE_TELEGRAM:-muma-telegram}"
IMAGE_IMPORTER="${IMAGE_IMPORTER:-muma-importer}"
IMAGE_TOOLS="${IMAGE_TOOLS:-muma-tools}"
# Resolved now: the lms env file loaded next may carry a DOCKER_USER of its own.
# Base first: muma:refresh-downloader builds FROM muma-base:latest, and must not
# find a base older than the images that were built on top of it.
MUMA_IMAGES=()
for image in "$IMAGE_BASE" "$IMAGE_DOWNLOADER" "$IMAGE_TELEGRAM" "$IMAGE_IMPORTER" "$IMAGE_TOOLS" "$IMAGE_CORE"; do
    MUMA_IMAGES+=("${DOCKER_USER}/${image}")
done
dotenv_load "$PROMOTE_LMS_ENV_FILE"
if [ -z "${IMAGE_NAME:-}" ]; then
    echo "Error: IMAGE_NAME is not set in the lms env file."
    exit 1
fi

docker_hub_login

USE_IMAGETOOLS=0
if docker buildx version >/dev/null 2>&1; then
    USE_IMAGETOOLS=1
fi

# promote SOURCE TARGET...: point every TARGET tag at the image SOURCE names.
promote() {
    local source="$1"
    shift
    local target
    if [ "$USE_IMAGETOOLS" = 1 ]; then
        for target in "$@"; do
            echo "--- ${source} -> ${target} ---"
            docker buildx imagetools create --tag "$target" "$source"
        done
        return 0
    fi
    echo "--- pulling ${source} ---"
    docker pull "$source"
    for target in "$@"; do
        echo "--- ${source} -> ${target} ---"
        docker tag "$source" "$target"
        docker push "$target"
    done
}

for image in "${MUMA_IMAGES[@]}"; do
    promote "${image}:${RELEASE_VERSION}" "${image}:latest"
done
promote "${IMAGE_NAME}:${RELEASE_VERSION}" "${IMAGE_NAME}:latest" "${IMAGE_NAME}:stable"

echo "--- :latest now points at ${RELEASE_VERSION} for every image this repository builds ---"
