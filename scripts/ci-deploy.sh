#!/bin/bash
# scripts/ci-deploy.sh
# Entry point for GitLab CI to deploy to production.
#
# Fully automated, idempotent deployment of BOTH production stacks:
#   1. "music-management" (db, music-manager, importer/downloader workers, ...)
#      -> docker/docker-compose.yml
#   2. "lms" (the Spotify UI + reverse-proxy, serving spotify.<domain> and the
#      OpenSubsonic API used by Ultrasonic/other Subsonic clients)
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

# Target configuration for Production
export REMOTE_HOST="${PROD_REMOTE_HOST:-192.0.2.27}"
export REMOTE_USER="${PROD_REMOTE_USER:-root}"

echo "--- Setting up SSH access to $REMOTE_HOST ---"

# 1. Configure ssh-agent from the SSH_PRIVATE_KEY CI/CD variable so none of
#    the deploy scripts need a password/sshpass.
if [ -z "${SSH_PRIVATE_KEY}" ]; then
    echo "Error: SSH_PRIVATE_KEY CI/CD variable is not set. See docs/deployment.md."
    exit 1
fi

eval "$(ssh-agent -s)" > /dev/null
KEY_FILE="$(mktemp)"
# SSH_PRIVATE_KEY is a "file" type CI/CD variable: its value is the path to a
# temp file already containing the key content when injected by the runner.
if [ -f "${SSH_PRIVATE_KEY}" ]; then
    cp "${SSH_PRIVATE_KEY}" "$KEY_FILE"
else
    printf '%s\n' "${SSH_PRIVATE_KEY}" > "$KEY_FILE"
fi
chmod 600 "$KEY_FILE"
ssh-add "$KEY_FILE"
rm -f "$KEY_FILE"

mkdir -p ~/.ssh
ssh-keyscan -H "$REMOTE_HOST" >> ~/.ssh/known_hosts 2>/dev/null || true

# Ensure SSH is working
if ! ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" "docker version" > /dev/null 2>&1; then
    echo "Error: Cannot connect to ${REMOTE_HOST} via SSH with the configured SSH_PRIVATE_KEY."
    exit 1
fi
echo "--- SSH access confirmed ---"

# 2. Materialize the .env files for both stacks from CI/CD variables (since
#    .env is gitignored and would otherwise not exist on a fresh checkout).
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

# 3. Provision the reverse-proxy nginx config on the remote host (this used
#    to be a manual copy step, see docs/deployment.md).
echo "--- Provisioning nginx reverse-proxy config on $REMOTE_HOST ---"
ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p /docker/lms/nginx"
scp -o StrictHostKeyChecking=no \
    "$PROJECT_ROOT/services/music-management-server/nginx/reverse-proxy.conf" \
    "${REMOTE_USER}@${REMOTE_HOST}:/docker/lms/nginx/reverse-proxy.conf"

# 4. Deploy stack 1: "music-management"
echo "--- Deploying stack: music-management ---"
export DEPLOY_TARGET_NAME="music-management"
export LOCAL_COMPOSE_FILE="docker/docker-compose.yml"
export LOCAL_ENV_FILE=".env"
"$SCRIPT_DIR/deploy.sh"

# 5. Deploy stack 2: "lms"
echo "--- Deploying stack: lms ---"
(
    cd "$PROJECT_ROOT/services/music-management-server"
    export DEPLOY_TARGET_NAME="lms"
    export LOCAL_COMPOSE_FILE="$PROJECT_ROOT/services/music-management-server/docker-compose.yml"
    export LOCAL_ENV_FILE="$PROJECT_ROOT/services/music-management-server/.env"
    "$PROJECT_ROOT/services/music-management-server/scripts/deploy-stack.sh"
)

# 6. Post-deploy verification: confirm both stacks report freshly (re)started
#    containers, so a silently-failed "up -d" doesn't get reported as success.
echo "--- Verifying container state on $REMOTE_HOST ---"
ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" \
    "docker ps --filter 'label=com.docker.compose.project=music-management' --filter 'label=com.docker.compose.project=lms' --format '{{.Names}}\t{{.Status}}'"

echo "--- CI Deployment finished successfully ---"
