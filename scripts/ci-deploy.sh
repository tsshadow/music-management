#!/bin/bash
# scripts/ci-deploy.sh
# Entry point for GitLab CI to deploy to production.
# Assumes SSH access is already configured on the runner (e.g. via SSH_PRIVATE_KEY variable).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Target configuration for Production
export REMOTE_HOST="${PROD_REMOTE_HOST:-192.0.2.27}"
export REMOTE_USER="${PROD_REMOTE_USER:-root}"
export DEPLOY_TARGET_NAME="${PROD_STACK_NAME:-muma}"
export LOCAL_COMPOSE_FILE="docker/docker-compose.yml"

echo "--- Starting CI Deployment to $REMOTE_HOST ($DEPLOY_TARGET_NAME) ---"

# Ensure SSH is working
if ! ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" "docker version" > /dev/null 2>&1; then
    echo "Error: Cannot connect to ${REMOTE_HOST} via SSH. Ensure SSH_PRIVATE_KEY is set in GitLab CI variables and the runner has access."
    exit 1
fi

# Run the main deployment script
# Note: We don't pass a password here, assuming SSH key auth is set up in CI
"$SCRIPT_DIR/deploy.sh"

echo "--- CI Deployment finished successfully ---"
