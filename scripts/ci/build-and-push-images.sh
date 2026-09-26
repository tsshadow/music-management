#!/bin/bash
# scripts/ci/build-and-push-images.sh
#
# Builds and pushes ALL Docker images that production actually pulls, from CI,
# on a release/* branch, *before* muma:deploy runs. This closes the gap that
# caused muma:deploy to only ever "docker compose pull" whatever image was
# last pushed manually (often stale/old) - see docs/release-management.md and
# CHANGELOG.md 0.0.2 for the full story.
#
# NOTE: this originally only covered music-manager/lms (bullets 1-2 below).
# See docs/bug-reports/007-telegram-session-schema-mismatch.md: a fix to the
# telegram worker's Dockerfile/dependencies went through a full green
# release/muma:deploy pipeline but never actually reached production, because
# nothing in CI ever rebuilt+pushed the muma-telegram (or muma-downloader/
# muma-importer/muma-tools/muma-base) images - "docker compose pull" just kept
# re-pulling the same old manually-pushed ":latest" tag. Bullets 3-6 close
# that gap for every image docker/docker-compose.yml actually references.
#
# Tags: every image is pushed as ":${VERSION}" and ":rc" -- never ":latest"
# (nor ":stable" for lms). Those are the tags production pulls, and Watchtower
# on the host pulls ":latest" of the downloader family the moment it changes;
# pushed from here, a release's code could start before muma:deploy had applied
# its migrations, or ship with no deploy at all. muma:deploy moves them, after
# the pre-deploy backup and the migrations, in
# scripts/ci/promote-release-images.sh. See
# docs/bug-reports/050-deploy-starts-new-code-before-migrations.md.
#
#   1. music-manager  (docker/Dockerfile.music-manager, build context: repo root)
#      -> "${DOCKER_USER}/${IMAGE_CORE}" (docker/docker-compose.yml's
#         `image: ${DOCKER_USER}/${IMAGE_CORE}:${IMAGE_TAG:-latest}`).
#   2. lms / music-management-server (services/music-management-server/Dockerfile-release,
#      build context: repo root)
#      -> "${IMAGE_NAME}", also as ":${LMS_VERSION}" (the C++ project's own
#         version, which does not move every release -- hence ":${VERSION}" as
#         the tag promotion copies from). Production pulls `${IMAGE_NAME}:${LMS_TAG}`,
#         and promotion moves both ":latest" and ":stable", so either value works.
#   3. muma-base (docker/Dockerfile.base) - common base image for 4-6 below.
#      Not referenced directly by docker-compose.yml, but must be rebuilt
#      first and pushed so the FROM ${DOCKER_USER}/muma-base:${VERSION} in the
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
#   - PROD_ENV_FILE, PROD_ENV_FILE_LMS: same file-type variables muma:deploy
#     already uses, needed here too so IMAGE_CORE/IMAGE_NAME/IMAGE_* resolve
#     to the exact same values docker-compose.yml will pull on the
#     production host.
#
# This job is gated in .gitlab-ci.yml on DOCKERHUB_USERNAME/DOCKERHUB_TOKEN
# being present, but since it runs before muma:deploy (same "release" stage,
# earlier than the "deploy" stage), a missing/failed build here blocks
# muma:deploy from ever running against a stale image.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# PUSH_IMAGES=false builds every image and pushes none of it.
#
# That mode exists for the muma:images job, which runs on merge requests
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

# The throwaway namespace a no-push run builds under.
#
# It used to be the fixed string "muma-ci", which meant every concurrent
# muma:images job wrote the same tags into the one image store the
# runner has. Seen on pipeline 2074 (2026-08-31, six pipelines at once): the job
# built muma-ci/muma-base:0.39.0, used it for the downloader image, and 80
# seconds later failed on the telegram image with
#
#   #4 [internal] load metadata for docker.io/muma-ci/muma-base:0.39.0
#   #4 ERROR: pull access denied, repository does not exist or may require authorization
#
# A sibling job had retagged the name out from under it, so buildkit went
# looking for it on Docker Hub -- where "muma-ci" does not and should not exist.
# The error reads as a missing credential and is nothing of the sort. Same
# defect db-integration.sh had before it keyed its container name on CI_JOB_ID.
#
# Outside CI there is no CI_JOB_ID, so the PID keeps two hand-runs on one
# machine apart.
THROWAWAY_NS="muma-ci-${CI_JOB_ID:-local-$$}"

# Applied after every `source` of a .env file below, because those files carry a
# DOCKER_USER/IMAGE_NAME of their own and would otherwise put the shared name
# back. Only the repository half is forced: two jobs under different namespaces
# cannot collide no matter what the rest of the name is.
scope_image_names() {
    if [ "$PUSH_IMAGES" != "true" ]; then
        DOCKER_USER="$THROWAWAY_NS"
        IMAGE_NAME="${THROWAWAY_NS}/lms"
    fi
}

# A no-push run proves the build and then has no use for what it built. Left
# behind, every job would strand a full set of images under a namespace no later
# job ever reuses -- the runner's disk janitor keeps ":latest" per repository, so
# these would accumulate rather than age out. Removed by tag rather than by image
# id, so no `-f` is needed: the shared id goes when its last tag does.
cleanup_throwaway_images() {
    [ "$PUSH_IMAGES" = "true" ] && return 0
    echo "--- Removing throwaway images under ${THROWAWAY_NS}/ ---"
    docker images --filter "reference=${THROWAWAY_NS}/*" --format '{{.Repository}}:{{.Tag}}' \
        | xargs -r docker rmi 2>/dev/null || true
}

# shellcheck source=scripts/ci/docker-hub-session.sh
. "$SCRIPT_DIR/docker-hub-session.sh"

# The prod .env files are materialized here, outside the checkout: the repo root
# is the build context of every image below, and .dockerignore is the only
# other thing keeping a .env in the checkout out of an image.
ENV_DIR="$(mktemp -d)"
chmod 700 "$ENV_DIR"
ROOT_ENV_FILE="$ENV_DIR/music-management.env"
LMS_ENV_FILE="$ENV_DIR/lms.env"

# cleanup_on_exit: everything this script leaves behind -- throwaway images,
# the Docker Hub session and the materialized env files.
cleanup_on_exit() {
    cleanup_throwaway_images
    docker_hub_logout
    rm -rf "$ENV_DIR"
}
trap cleanup_on_exit EXIT

# docker_push IMAGE: push IMAGE, or only say so when PUSH_IMAGES=false.
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
# muma:deploy uses, so IMAGE_CORE/DOCKER_USER/IMAGE_NAME/LMS_TAG match exactly
# what production will pull (jobs don't share a filesystem, so this has to be
# redone here rather than relying on what ci-deploy.sh writes in a later job).
# write_env_file VALUE DEST: write a file-type CI/CD variable (a path) or a
# plain one (the content itself) to DEST, readable by the owner only.
write_env_file() {
    local var_value="$1"
    local dest="$2"
    (
        umask 077
        if [ -f "${var_value}" ]; then
            cp "${var_value}" "$dest"
        else
            printf '%s\n' "${var_value}" > "$dest"
        fi
    )
}

if [ "$PUSH_IMAGES" = "true" ]; then
    if [ -z "${PROD_ENV_FILE}" ]; then
        echo "Error: PROD_ENV_FILE CI/CD variable is not set. See docs/deployment.md."
        exit 1
    fi
    write_env_file "${PROD_ENV_FILE}" "$ROOT_ENV_FILE"

    if [ -z "${PROD_ENV_FILE_LMS}" ]; then
        echo "Error: PROD_ENV_FILE_LMS CI/CD variable is not set. See docs/deployment.md."
        exit 1
    fi
    write_env_file "${PROD_ENV_FILE_LMS}" "$LMS_ENV_FILE"

    docker_hub_login
else
    # No push means no production secrets: a merge-request pipeline must not
    # need PROD_ENV_FILE at all. The image *names* are the only thing those
    # files contribute to a build, and a build proves the same thing under a
    # throwaway name. Written rather than skipped because the script sources
    # both files under `set -e`.
    #
    # A developer's own .env in the checkout is still honoured when this is run
    # by hand -- read, never overwritten. In CI there is none (.env is
    # gitignored), so the placeholders apply.
    echo "--- PUSH_IMAGES=false: building under ${THROWAWAY_NS}/, no Docker Hub login ---"
    if [ -f "$PROJECT_ROOT/.env" ]; then
        ROOT_ENV_FILE="$PROJECT_ROOT/.env"
    else
        printf 'DOCKER_USER=%s\nIMAGE_CORE=music-manager\n' "$THROWAWAY_NS" > "$ROOT_ENV_FILE"
    fi
    if [ -f "$PROJECT_ROOT/services/music-management-server/.env" ]; then
        LMS_ENV_FILE="$PROJECT_ROOT/services/music-management-server/.env"
    else
        printf 'IMAGE_NAME=%s/lms\n' "$THROWAWAY_NS" > "$LMS_ENV_FILE"
    fi
fi

VERSION=$(cat VERSION 2>/dev/null || echo "latest")

# 1. Build + push music-manager -----------------------------------------------
set -a
# shellcheck disable=SC1090,SC1091 # a per-run env file, path known only at runtime
source "$ROOT_ENV_FILE"
set +a
DOCKER_USER="${DOCKER_USER:-$DOCKERHUB_USERNAME}"
IMAGE_CORE="${IMAGE_CORE:-music-manager}"
scope_image_names

echo "--- Building music-manager image (${DOCKER_USER}/${IMAGE_CORE}:${VERSION}) ---"
docker build \
    --build-arg DOCKER_USER="${DOCKER_USER}" \
    --build-arg VERSION="${VERSION}" \
    -t "${DOCKER_USER}/${IMAGE_CORE}:rc" \
    -t "${DOCKER_USER}/${IMAGE_CORE}:${VERSION}" \
    -f docker/Dockerfile.music-manager .

echo "--- Pushing music-manager image ---"
docker_push "${DOCKER_USER}/${IMAGE_CORE}:rc"
docker_push "${DOCKER_USER}/${IMAGE_CORE}:${VERSION}"

# 2. Build + push lms (music-management-server) -------------------------------
set -a
# shellcheck disable=SC1090,SC1091 # a per-run env file, path known only at runtime
source "$LMS_ENV_FILE"
set +a
scope_image_names
if [ -z "${IMAGE_NAME}" ]; then
    echo "Error: IMAGE_NAME is not set in PROD_ENV_FILE_LMS."
    exit 1
fi
LMS_VERSION=$(grep "project(lms VERSION" services/music-management-server/CMakeLists.txt | sed 's/.*VERSION \(.*\))/\1/')

echo "--- Building lms image (${IMAGE_NAME}:${LMS_VERSION}) ---"
docker build \
    --build-arg VITE_GOOGLE_CLIENT_ID="${VITE_GOOGLE_CLIENT_ID}" \
    -t "${IMAGE_NAME}:rc" \
    -t "${IMAGE_NAME}:${VERSION}" \
    -t "${IMAGE_NAME}:${LMS_VERSION}" \
    -f services/music-management-server/Dockerfile-release .

echo "--- Pushing lms image ---"
docker_push "${IMAGE_NAME}:rc"
docker_push "${IMAGE_NAME}:${VERSION}"
docker_push "${IMAGE_NAME}:${LMS_VERSION}"

# 3. Build + push muma-base ----------------------------------------------------
# (re-source root .env: sourcing PROD_ENV_FILE_LMS above may have shadowed
# some of its variables since both files are sourced into the same shell)
set -a
# shellcheck disable=SC1090,SC1091 # a per-run env file, path known only at runtime
source "$ROOT_ENV_FILE"
set +a
DOCKER_USER="${DOCKER_USER:-$DOCKERHUB_USERNAME}"
IMAGE_BASE="${IMAGE_BASE:-muma-base}"
IMAGE_DOWNLOADER="${IMAGE_DOWNLOADER:-muma-downloader}"
IMAGE_TELEGRAM="${IMAGE_TELEGRAM:-muma-telegram}"
IMAGE_IMPORTER="${IMAGE_IMPORTER:-muma-importer}"
IMAGE_TOOLS="${IMAGE_TOOLS:-muma-tools}"
scope_image_names

echo "--- Building muma-base image (${DOCKER_USER}/${IMAGE_BASE}:${VERSION}) ---"
docker build \
    -t "${DOCKER_USER}/${IMAGE_BASE}:rc" \
    -t "${DOCKER_USER}/${IMAGE_BASE}:${VERSION}" \
    -f docker/Dockerfile.base .

echo "--- Pushing muma-base image ---"
docker_push "${DOCKER_USER}/${IMAGE_BASE}:rc"
docker_push "${DOCKER_USER}/${IMAGE_BASE}:${VERSION}"

# 4. Build + push muma-downloader ----------------------------------------------
echo "--- Building muma-downloader image (${DOCKER_USER}/${IMAGE_DOWNLOADER}:${VERSION}) ---"
docker build \
    --build-arg DOCKER_USER="${DOCKER_USER}" \
    --build-arg VERSION="${VERSION}" \
    -t "${DOCKER_USER}/${IMAGE_DOWNLOADER}:rc" \
    -t "${DOCKER_USER}/${IMAGE_DOWNLOADER}:${VERSION}" \
    -f docker/Dockerfile.downloader .

echo "--- Pushing muma-downloader image ---"
docker_push "${DOCKER_USER}/${IMAGE_DOWNLOADER}:rc"
docker_push "${DOCKER_USER}/${IMAGE_DOWNLOADER}:${VERSION}"

# 5. Build + push muma-telegram -------------------------------------------------
echo "--- Building muma-telegram image (${DOCKER_USER}/${IMAGE_TELEGRAM}:${VERSION}) ---"
docker build \
    --build-arg DOCKER_USER="${DOCKER_USER}" \
    --build-arg VERSION="${VERSION}" \
    -t "${DOCKER_USER}/${IMAGE_TELEGRAM}:rc" \
    -t "${DOCKER_USER}/${IMAGE_TELEGRAM}:${VERSION}" \
    -f docker/Dockerfile.telegram .

echo "--- Pushing muma-telegram image ---"
docker_push "${DOCKER_USER}/${IMAGE_TELEGRAM}:rc"
docker_push "${DOCKER_USER}/${IMAGE_TELEGRAM}:${VERSION}"

# 6. Build + push muma-importer -------------------------------------------------
echo "--- Building muma-importer image (${DOCKER_USER}/${IMAGE_IMPORTER}:${VERSION}) ---"
docker build \
    --build-arg DOCKER_USER="${DOCKER_USER}" \
    --build-arg VERSION="${VERSION}" \
    -t "${DOCKER_USER}/${IMAGE_IMPORTER}:rc" \
    -t "${DOCKER_USER}/${IMAGE_IMPORTER}:${VERSION}" \
    -f docker/Dockerfile.importer .

echo "--- Pushing muma-importer image ---"
docker_push "${DOCKER_USER}/${IMAGE_IMPORTER}:rc"
docker_push "${DOCKER_USER}/${IMAGE_IMPORTER}:${VERSION}"

# 7. Build + push muma-tools ----------------------------------------------------
echo "--- Building muma-tools image (${DOCKER_USER}/${IMAGE_TOOLS}:${VERSION}) ---"
docker build \
    -t "${DOCKER_USER}/${IMAGE_TOOLS}:rc" \
    -t "${DOCKER_USER}/${IMAGE_TOOLS}:${VERSION}" \
    -f docker/Dockerfile.tools .

echo "--- Pushing muma-tools image ---"
docker_push "${DOCKER_USER}/${IMAGE_TOOLS}:rc"
docker_push "${DOCKER_USER}/${IMAGE_TOOLS}:${VERSION}"

# In no-push mode, untag the per-version aliases before exiting. Every tag
# above points at the same image id as its :rc sibling, so this removes
# no layers and costs the next build nothing -- but without it every
# merge-request run of muma:images left a :${VERSION} tag behind, and
# each release bump orphaned the previous version's set on the runner's disk.
# The :rc tags stay: they are overwritten in place on the next run and are
# what keeps the build cache warm. (The runner LXC has filled up before; see
# the ops notes on per-pipeline image accumulation.)
if [ "$PUSH_IMAGES" != "true" ] && [ "$VERSION" != "latest" ]; then
    echo "--- PUSH_IMAGES=false: untagging per-version aliases ---"
    docker rmi \
        "${DOCKER_USER}/${IMAGE_CORE}:${VERSION}" \
        "${IMAGE_NAME}:${VERSION}" \
        "${IMAGE_NAME}:${LMS_VERSION}" \
        "${DOCKER_USER}/${IMAGE_BASE}:${VERSION}" \
        "${DOCKER_USER}/${IMAGE_DOWNLOADER}:${VERSION}" \
        "${DOCKER_USER}/${IMAGE_TELEGRAM}:${VERSION}" \
        "${DOCKER_USER}/${IMAGE_IMPORTER}:${VERSION}" \
        "${DOCKER_USER}/${IMAGE_TOOLS}:${VERSION}" \
        >/dev/null 2>&1 || true
fi

echo "--- build-and-push-images.sh completed: music-manager, lms, and all background worker images (base/downloader/telegram/importer/tools) are now up to date on Docker Hub ---"
