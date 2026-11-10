#!/bin/bash
# scripts/ci/release-image-names.sh
#
# The names of the images a release pushes, in one place. Sourced by
# build-and-push-images.sh, refresh-downloader-image.sh and dependency-audit.sh.
#
# Each name comes from a plain CI/CD variable of the same name, else from the
# default below. No production env file is read: the image names are not
# secret, and this repository has no production variables (docs/designs/ops-split/).
#
#   DOCKER_USER        registry user the images live under; default DOCKERHUB_USERNAME
#   IMAGE_CORE         music-manager
#   IMAGE_BASE         muma-base (docker/Dockerfile.* name it in FROM; keep it)
#   IMAGE_DOWNLOADER   muma-downloader
#   IMAGE_TELEGRAM     muma-telegram
#   IMAGE_IMPORTER     muma-importer
#   IMAGE_TOOLS        muma-tools
#   IMAGE_LMS          lms; the player image is ${DOCKER_USER}/${IMAGE_LMS}
#
# The installation that pulls them must use the same names in its .env files
# (DOCKER_USER, IMAGE_*, and IMAGE_NAME=${DOCKER_USER}/${IMAGE_LMS} for the player).
#
# Meant to be sourced. Sets the variables above and LMS_IMAGE (the full player
# image name). Returns 1 when no registry user is known.

# resolve_release_image_names: set every image name from its variable or default.
resolve_release_image_names() {
    DOCKER_USER="${DOCKER_USER:-${DOCKERHUB_USERNAME:-}}"
    IMAGE_CORE="${IMAGE_CORE:-music-manager}"
    IMAGE_BASE="${IMAGE_BASE:-muma-base}"
    IMAGE_DOWNLOADER="${IMAGE_DOWNLOADER:-muma-downloader}"
    IMAGE_TELEGRAM="${IMAGE_TELEGRAM:-muma-telegram}"
    IMAGE_IMPORTER="${IMAGE_IMPORTER:-muma-importer}"
    IMAGE_TOOLS="${IMAGE_TOOLS:-muma-tools}"
    IMAGE_LMS="${IMAGE_LMS:-lms}"
    if [ -z "$DOCKER_USER" ]; then
        echo "Error: neither DOCKER_USER nor DOCKERHUB_USERNAME is set; the images have no registry user." >&2
        return 1
    fi
    # shellcheck disable=SC2034 # read by the scripts that source this file
    LMS_IMAGE="${DOCKER_USER}/${IMAGE_LMS}"
    return 0
}
