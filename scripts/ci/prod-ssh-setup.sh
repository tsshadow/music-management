#!/bin/bash
# scripts/ci/prod-ssh-setup.sh
#
# Shared SSH bootstrap for every job that talks to the production host.
#
# This used to live inline in scripts/ci-deploy.sh, which was fine while
# deploying was the only thing CI did over SSH. It no longer is: the
# post-deploy gate (scripts/ci/post-deploy-verify.sh) and the deployed-version
# check (scripts/ci/verify-prod-version.sh) both need the same agent, the same
# known_hosts entry and the same "can we actually reach it" probe. Three copies
# of that block is how they drift.
#
# Meant to be *sourced*, not executed: it exports REMOTE_HOST/REMOTE_USER for
# the caller and leaves an ssh-agent running in the caller's shell -- until that
# shell exits. The agent holds the production root key, and the runner is a
# shell executor shared by every pipeline, so an agent that outlived its job
# used to leave that key one SSH_AUTH_SOCK away from any later job on the same
# machine. It is now killed by an EXIT trap this file installs in the caller
# (prod_ssh_teardown), and the key is added with a lifetime as a second line of
# defence. A caller that needs an EXIT trap of its own must call
# prod_ssh_teardown from it, since a second `trap ... EXIT` replaces this one.
#
# Required CI/CD variable:
#   - SSH_PRIVATE_KEY: private key (file type) authorized on the production
#                      host (see docs/deployment.md).

# Target configuration for Production.
export REMOTE_HOST="${PROD_REMOTE_HOST:-192.0.2.27}"
export REMOTE_USER="${PROD_REMOTE_USER:-root}"

echo "--- Setting up SSH access to $REMOTE_HOST ---"

if [ -z "${SSH_PRIVATE_KEY}" ]; then
    echo "Error: SSH_PRIVATE_KEY CI/CD variable is not set. See docs/deployment.md."
    exit 1
fi

# prod_ssh_teardown: kill the ssh-agent started below, so the production key
# does not outlive the job. Safe to call more than once.
prod_ssh_teardown() {
    # Only non-empty if ssh-add failed before the key file could be removed.
    if [ -n "${KEY_FILE:-}" ]; then
        rm -f "$KEY_FILE"
    fi
    if [ -n "${PROD_SSH_AGENT_PID:-}" ]; then
        kill "$PROD_SSH_AGENT_PID" 2>/dev/null || true
        unset PROD_SSH_AGENT_PID SSH_AGENT_PID SSH_AUTH_SOCK
    fi
}

eval "$(ssh-agent -s)" > /dev/null
PROD_SSH_AGENT_PID="$SSH_AGENT_PID"
trap prod_ssh_teardown EXIT

# Longer than any job that sources this (muma:deploy has a 30-minute timeout),
# short enough that a leaked agent stops being useful on its own.
PROD_SSH_KEY_LIFETIME="${PROD_SSH_KEY_LIFETIME:-3600}"

KEY_FILE="$(mktemp)"
# SSH_PRIVATE_KEY is a "file" type CI/CD variable: its value is the path to a
# temp file already containing the key content when injected by the runner.
if [ -f "${SSH_PRIVATE_KEY}" ]; then
    cp "${SSH_PRIVATE_KEY}" "$KEY_FILE"
else
    printf '%s\n' "${SSH_PRIVATE_KEY}" > "$KEY_FILE"
fi
chmod 600 "$KEY_FILE"
ssh-add -t "$PROD_SSH_KEY_LIFETIME" "$KEY_FILE"
rm -f "$KEY_FILE"
KEY_FILE=""

mkdir -p ~/.ssh
ssh-keyscan -H "$REMOTE_HOST" >> ~/.ssh/known_hosts 2>/dev/null || true

# Ensure SSH is working.
if ! ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" "docker version" > /dev/null 2>&1; then
    echo "Error: Cannot connect to ${REMOTE_HOST} via SSH with the configured SSH_PRIVATE_KEY."
    exit 1
fi
echo "--- SSH access confirmed ---"
