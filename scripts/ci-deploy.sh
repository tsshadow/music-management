#!/bin/bash
# scripts/ci-deploy.sh
# Entry point for GitLab CI to deploy to production.
#
# Fully automated, idempotent deployment of BOTH production stacks:
#   1. "music-management" (db, music-manager, importer/downloader workers, ...)
#      -> docker/docker-compose.yml
#   2. "lms" (the Spotify UI + reverse-proxy, serving spotify.<domain> and the
#      OpenSubsonic API used by MuMa Mobile/other Subsonic clients)
#      -> services/music-management-server/docker-compose.yml
#
# Required GitLab CI/CD variables (Project > Settings > CI/CD > Variables):
#   - SSH_PRIVATE_KEY:     private key (file type) authorized on the
#                          production host (see docs/deployment.md).
#   - PROD_ENV_FILE:       full .env content (file type) for stack 1, since
#                          .env is gitignored and never present on a fresh
#                          checkout.
#   - PROD_ENV_FILE_LMS:   full .env content (file type) for stack 2.
# No manual step on the production host is required: SSH keys, .env content,
# and the nginx reverse-proxy config are all provisioned by this script.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# 1. Configure ssh-agent from the SSH_PRIVATE_KEY CI/CD variable so none of
#    the deploy scripts need a password/sshpass. Shared with the post-deploy
#    gate and the deployed-version check, which need the identical setup.
# shellcheck source=scripts/ci/prod-ssh-setup.sh
. "$SCRIPT_DIR/ci/prod-ssh-setup.sh"

# 2. Materialize the .env files for both stacks from CI/CD variables (since
#    .env is gitignored and would otherwise not exist on a fresh checkout).
#
#    Into a private temp directory, not into the checkout: the shell-executor
#    runner keeps its checkouts, so a prod .env written there outlived the job,
#    and the repo root is the build context of every image -- one `docker build
#    .` in a later job would have copied it in. Removed on exit together with
#    the ssh-agent (prod_ssh_teardown, from prod-ssh-setup.sh).
ENV_DIR="$(mktemp -d)"
chmod 700 "$ENV_DIR"

# cleanup_deploy: remove the materialized env files and stop the ssh-agent.
cleanup_deploy() {
    rm -rf "$ENV_DIR"
    prod_ssh_teardown
}
trap cleanup_deploy EXIT

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

if [ -z "${PROD_ENV_FILE}" ]; then
    echo "Error: PROD_ENV_FILE CI/CD variable is not set. See docs/deployment.md."
    exit 1
fi
write_env_file "${PROD_ENV_FILE}" "$ENV_DIR/music-management.env"

if [ -z "${PROD_ENV_FILE_LMS}" ]; then
    echo "Error: PROD_ENV_FILE_LMS CI/CD variable is not set. See docs/deployment.md."
    exit 1
fi
write_env_file "${PROD_ENV_FILE_LMS}" "$ENV_DIR/lms.env"

# 3. Provision the reverse-proxy nginx config on the remote host (this used
#    to be a manual copy step, see docs/deployment.md).
echo "--- Provisioning nginx reverse-proxy config on $REMOTE_HOST ---"
ssh "${PROD_SSH_OPTS[@]}" "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p /docker/lms/nginx"
scp "${PROD_SSH_OPTS[@]}" \
    "$PROJECT_ROOT/services/music-management-server/nginx/reverse-proxy.conf" \
    "${REMOTE_USER}@${REMOTE_HOST}:/docker/lms/nginx/reverse-proxy.conf"

# 4. Deploy stack 1: "music-management"
#
#    deploy.sh backs the database up, migrates, and only then runs the pre-up
#    hook below, which moves the release's images from :${VERSION} to :latest
#    (release:build-images no longer pushes :latest at all). Until that moment
#    Watchtower on the host has nothing new to pull, so no container can start
#    this release's code before its migrations have been applied -- and a
#    pipeline whose muma:deploy never runs never changes :latest. The stack
#    itself is then pulled at :latest (IMAGE_TAG unset), which keeps the
#    downloader family on the tag muma:refresh-downloader republishes.
#    See docs/bug-reports/050-deploy-starts-new-code-before-migrations.md.
echo "--- Deploying stack: music-management ---"
export DEPLOY_TARGET_NAME="music-management"
export LOCAL_COMPOSE_FILE="docker/docker-compose.yml"
export LOCAL_ENV_FILE="$ENV_DIR/music-management.env"
export DEPLOY_PRE_UP_HOOK="$SCRIPT_DIR/ci/promote-release-images.sh"
export PROMOTE_ENV_FILE="$ENV_DIR/music-management.env"
export PROMOTE_LMS_ENV_FILE="$ENV_DIR/lms.env"
"$SCRIPT_DIR/deploy.sh"
unset DEPLOY_PRE_UP_HOOK

# 5. Deploy stack 2: "lms"
echo "--- Deploying stack: lms ---"
(
    cd "$PROJECT_ROOT/services/music-management-server"
    export DEPLOY_TARGET_NAME="lms"
    export LOCAL_COMPOSE_FILE="$PROJECT_ROOT/services/music-management-server/docker-compose.yml"
    export LOCAL_ENV_FILE="$ENV_DIR/lms.env"
    "$PROJECT_ROOT/services/music-management-server/scripts/deploy-stack.sh"
)

# 6. Post-deploy verification. This step used to run two `docker ps --format`
#    calls purely for their stdout and then echo "finished successfully"
#    unconditionally - `docker ps` exits 0 for a restart-looping container and
#    for an empty stack alike, so the deploy could not fail here even when
#    nothing was serving. The real checks now live in post-deploy-verify.sh,
#    which exits non-zero, and which the muma:verify job re-runs afterwards.
"$SCRIPT_DIR/ci/post-deploy-verify.sh"

# 7. Prune the images nothing needs any more, now that the release is verified
#    (bug report 094: every deploy pulled new images and none were ever removed,
#    until the root disk was 95% full). Keeps every image a container uses and,
#    per repository, the PRUNE_KEEP_RELEASES (3) previous ones for an IMAGE_TAG
#    rollback. Only after step 6: an unverified release may still need the
#    images it replaced. A failed prune is a warning, not a failed deploy --
#    the next deploy's disk pre-check is what stops on a full disk.
if ! "$SCRIPT_DIR/ci/prune-prod-images.sh"; then
    echo "WARNING: pruning old images on $REMOTE_HOST failed; the deploy itself succeeded. See docs/deployment.md#disk-space-on-the-production-host."
fi

echo "--- CI Deployment finished successfully ---"
