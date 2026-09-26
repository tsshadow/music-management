#!/bin/bash
# Generalized Docker Stack Deployment Script
# Supports: Portainer discovery, SSH transfer, Service-specific updates, and Initial creation.

set -e

# Host key checking for run_ssh below: pinned for production, accept-new elsewhere.
# shellcheck source=scripts/lib/ssh_host_keys.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)/scripts/lib/ssh_host_keys.sh"

# Nothing secret may appear on a command line in this script: argv is readable
# through `ps` by every account on the runner and on the production host. The
# env file travels on ssh's stdin instead. See
# docs/bug-reports/038-deploy-puts-every-prod-secret-on-the-command-line.md.

# run_ssh HOST USER PASS CMD: run CMD on HOST, passing this shell's stdin through.
# CMD itself must never contain a secret. The password, when one is used, goes
# to sshpass through the SSHPASS environment variable rather than `-p`.
run_ssh() {
    local host="$1"
    local user="$2"
    local pass="$3"
    local cmd="$4"
    
    if [ -z "$host" ] || [ -z "$user" ]; then
        return 1
    fi

    # Pinned host key for production, accept-new elsewhere (scripts/lib/ssh_host_keys.sh).
    local -a key_opts
    mapfile -t key_opts < <(ssh_host_key_opts "$host")

    if [ -z "$pass" ]; then
        ssh "${key_opts[@]}" "${user}@${host}" "${cmd}"
    elif command -v sshpass >/dev/null 2>&1; then
        SSHPASS="${pass}" sshpass -e ssh "${key_opts[@]}" "${user}@${host}" "${cmd}"
    else
        echo "Error: sshpass not found. Install it or unset password variable."
        exit 1
    fi
}

# Parameters (usually from environment)
STACK_NAME="${DEPLOY_TARGET_NAME}"
STACK_NAME=$(echo "$STACK_NAME" | tr '[:upper:]' '[:lower:]')
SERVICE_NAME="${SERVICE_NAME:-$2}"
IMAGE_NAME="${IMAGE_NAME}"
TAG="${TAG:-$4}"
SEARCH_STRING="${SEARCH_STRING:-$IMAGE_NAME}"
LOCAL_ENV_FILE="${LOCAL_ENV_FILE:-$5}"
EXTRA_VARS="${EXTRA_VARS}"

# Discovery command to be run on remote hosts
DISCOVERY_CMD="
    ACTUAL_COMPOSE_FILE=\"\"
    # 1. Try to find via running container labels for the target project
    if [ -n \"$STACK_NAME\" ]; then
        CONTAINER_ID=\$(docker ps -q --filter \"label=com.docker.compose.project=$STACK_NAME\" | head -n 1)
        if [ -n \"\$CONTAINER_ID\" ]; then
            ACTUAL_COMPOSE_FILE=\$(docker inspect \"\$CONTAINER_ID\" --format '{{ index .Config.Labels \"com.docker.compose.project.config_files\" }}' 2>/dev/null | cut -d, -f1)
        fi
    fi
    # 2. Try to find via SERVICE_NAME label
    if ([ -z \"\$ACTUAL_COMPOSE_FILE\" ] || [ ! -f \"\$ACTUAL_COMPOSE_FILE\" ]) && [ -n \"$SERVICE_NAME\" ]; then
        ACTUAL_COMPOSE_FILE=\$(docker inspect \"$SERVICE_NAME\" --format '{{ index .Config.Labels \"com.docker.compose.project.config_files\" }}' 2>/dev/null | cut -d, -f1)
    fi
    # 3. Fallback to provided path
    if ([ -z \"\$ACTUAL_COMPOSE_FILE\" ] || [ ! -f \"\$ACTUAL_COMPOSE_FILE\" ]) && [ -n \"$REMOTE_STACK_PATH\" ]; then
        if [ -f \"\$REMOTE_STACK_PATH\" ]; then ACTUAL_COMPOSE_FILE=\"\$REMOTE_STACK_PATH\"; fi
    fi
    # 4. Search common paths
    if [ -z \"\$ACTUAL_COMPOSE_FILE\" ] || [ ! -f \"\$ACTUAL_COMPOSE_FILE\" ]; then
        for SEARCH_DIR in /data/compose /var/lib/docker/volumes/*/ _data/compose /var/lib/docker/volumes/portainer_portainer_data/_data/compose; do
            if [ -d \"\$SEARCH_DIR\" ]; then
                MATCH=\$(grep -rl \"$SEARCH_STRING\" \"\$SEARCH_DIR\" 2>/dev/null | grep \"docker-compose.yml\" | head -n 1)
                if [ -f \"\$MATCH\" ]; then ACTUAL_COMPOSE_FILE=\"\$MATCH\"; break; fi
            fi
        done
    fi
    if [ -n \"\$ACTUAL_COMPOSE_FILE\" ] && [ -f \"\$ACTUAL_COMPOSE_FILE\" ]; then
        echo \"FOUND_FILE:\$ACTUAL_COMPOSE_FILE\"
        cat \"\$ACTUAL_COMPOSE_FILE\"
    fi
"

COMPOSE_CONTENT=""

# 1. Use local compose file if provided (Source of truth for deployment)
if [ -n "$LOCAL_COMPOSE_FILE" ] && [ -f "$LOCAL_COMPOSE_FILE" ]; then
    echo "Using local configuration file: $LOCAL_COMPOSE_FILE"
    COMPOSE_CONTENT=$(expand -t 4 "$LOCAL_COMPOSE_FILE")
fi

# 2. Try discovery on PORTAINER_HOST if local not provided
if [ -z "$COMPOSE_CONTENT" ] && [ -n "$PORTAINER_HOST" ]; then
    echo "Checking Portainer host $PORTAINER_HOST for stack template..."
    P_USER="${PORTAINER_HOST_USER:-$REMOTE_USER}"
    P_PASS="${PORTAINER_HOST_PASS:-$REMOTE_PASS}"
    RESULT=$(run_ssh "$PORTAINER_HOST" "$P_USER" "$P_PASS" "REMOTE_STACK_PATH='$REMOTE_STACK_PATH' $DISCOVERY_CMD" 2>/dev/null || true)
    if echo "$RESULT" | grep -q "^FOUND_FILE:"; then
        COMPOSE_CONTENT=$(echo "$RESULT" | sed -n '/^FOUND_FILE:/!p' | expand -t 4)
        echo "Found template on $PORTAINER_HOST"
    fi
fi

# 3. Try discovery on REMOTE_HOST if still not found
if [ -z "$COMPOSE_CONTENT" ] && [ -n "$REMOTE_HOST" ]; then
    echo "Checking remote host $REMOTE_HOST for existing configuration..."
    RESULT=$(run_ssh "$REMOTE_HOST" "$REMOTE_USER" "$REMOTE_PASS" "REMOTE_STACK_PATH='$REMOTE_STACK_PATH' $DISCOVERY_CMD" 2>/dev/null || true)
    if echo "$RESULT" | grep -q "^FOUND_FILE:"; then
        COMPOSE_CONTENT=$(echo "$RESULT" | sed -n '/^FOUND_FILE:/!p' | expand -t 4)
        echo "Found existing configuration on $REMOTE_HOST"
    fi
fi

if [ -z "$COMPOSE_CONTENT" ]; then
    echo "Error: No docker-compose configuration found (tried Portainer, Remote, and Local)."
    exit 1
fi

# The compose file is no secret (it is the tracked file), so it may ride on the
# command line; the env file may not.
B64_DATA=$(echo "$COMPOSE_CONTENT" | base64 -w 0)
SEND_ENV=0
if [ -n "$LOCAL_ENV_FILE" ] && [ -f "$LOCAL_ENV_FILE" ]; then
    SEND_ENV=1
fi

# Final deployment logic to be run on REMOTE_HOST
#
# Everything lands in a root-only directory under the remote user's home, not
# in world-writable /tmp: a file another account can pre-create or swap there is
# a file root would hand to compose. The compose file stays (it holds no
# secrets, and the container labels point at it); the env file is written into a
# per-run directory that the EXIT trap removes once compose is done with it.
# compose only reads --env-file while it parses the project. A run killed before
# its trap fired is cleaned up by the next one (the rm of run.*).
#
# The env content arrives on stdin, never on the command line.
DEPLOY_CMD="
    set -e
    umask 077
    DEPLOY_ROOT=\"\${HOME:?}/.muma-deploy\"
    DEPLOY_DIR=\"\$DEPLOY_ROOT/$STACK_NAME\"
    mkdir -p \"\$DEPLOY_DIR\"
    chmod 700 \"\$DEPLOY_ROOT\" \"\$DEPLOY_DIR\"
    rm -rf \"\$DEPLOY_DIR\"/run.*
    RUN_DIR=\$(mktemp -d \"\$DEPLOY_DIR/run.XXXXXX\")
    trap 'rm -rf \"\$RUN_DIR\"' EXIT
    trap 'exit 1' HUP INT TERM

    FINAL_COMPOSE_FILE=\"\$DEPLOY_DIR/docker-compose.yml\"
    echo '$B64_DATA' | base64 -d > \"\$FINAL_COMPOSE_FILE\"

    # Handle environment variables
    ENV_ARG=\"\"
    if [ \"$SEND_ENV\" = 1 ]; then
        FINAL_ENV_FILE=\"\$RUN_DIR/.env\"
        cat > \"\$FINAL_ENV_FILE\"
        ENV_ARG=\"--env-file \$FINAL_ENV_FILE\"
        echo \"Using environment file: \$FINAL_ENV_FILE (removed when this deploy ends)\"
    fi

    # Selection of compose command. Only root-owned locations are consulted:
    # this runs as root, and an executable any local account could drop into
    # /tmp would be run as root on the next deploy.
    if [ -x /usr/local/bin/docker-compose-v2 ]; then
        DOCKER_CMD=\"/usr/local/bin/docker-compose-v2 \$ENV_ARG -f \$FINAL_COMPOSE_FILE -p $STACK_NAME\"
    elif docker compose version >/dev/null 2>&1; then
        DOCKER_CMD=\"docker compose \$ENV_ARG -f \$FINAL_COMPOSE_FILE -p $STACK_NAME\"
    elif command -v docker-compose >/dev/null 2>&1; then
        DOCKER_CMD=\"docker-compose \$ENV_ARG -f \$FINAL_COMPOSE_FILE -p $STACK_NAME\"
    else
        echo \"Error: Neither docker compose nor docker-compose found on remote host.\"
        exit 1
    fi
    
    echo \"Updating stack '$STACK_NAME' via: \$DOCKER_CMD\"
    
    # Inject extra variables if provided
    if [ -n \"$EXTRA_VARS\" ]; then
        echo \"Injecting extra variables: $EXTRA_VARS\"
        export $EXTRA_VARS
    fi

    \$DOCKER_CMD pull
    
    if [ -n \"$SERVICE_NAME\" ] && \$DOCKER_CMD config --services | grep -q \"^$SERVICE_NAME\$\"; then
        echo \"Updating service: $SERVICE_NAME\"
        \$DOCKER_CMD up -d --remove-orphans $SERVICE_NAME
    else
        echo \"Updating full stack...\"
        \$DOCKER_CMD up -d --remove-orphans
    fi
"

if [ "$SEND_ENV" = 1 ]; then
    run_ssh "$REMOTE_HOST" "$REMOTE_USER" "$REMOTE_PASS" "$DEPLOY_CMD" < "$LOCAL_ENV_FILE"
else
    run_ssh "$REMOTE_HOST" "$REMOTE_USER" "$REMOTE_PASS" "$DEPLOY_CMD" < /dev/null
fi

echo "--- Stack '$STACK_NAME' deployment completed successfully ---"
