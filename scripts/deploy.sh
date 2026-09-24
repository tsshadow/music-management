#!/bin/bash
# Comprehensive Docker Stack Deployment Script
# Handles: Webhooks, Remote SSH updates, and Database Migrations.

set -e

# Nothing secret may appear on a command line in this script: argv is readable
# through `ps` by every account on the runner and, for the remote half, on the
# production host. Secrets travel on ssh's stdin instead. See
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

    if [ -z "$pass" ]; then
        ssh -o StrictHostKeyChecking=no "${user}@${host}" "${cmd}"
    elif command -v sshpass >/dev/null 2>&1; then
        SSHPASS="${pass}" sshpass -e ssh -o StrictHostKeyChecking=no "${user}@${host}" "${cmd}"
    else
        echo "Error: sshpass not found. Install it or unset password variable."
        exit 1
    fi
}

# Ensure we are in the project root if possible, or handle relative paths
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=scripts/lib/dotenv.sh
. "$SCRIPT_DIR/lib/dotenv.sh"

# The env file is both the configuration of this script and the file shipped
# to the host for the stack. It may be absolute: ci-deploy.sh materialises it in
# a private temp directory, outside the checkout and therefore outside every
# docker build context.
LOCAL_ENV_FILE="${LOCAL_ENV_FILE:-.env}"
case "$LOCAL_ENV_FILE" in
    /*) ENV_PATH="$LOCAL_ENV_FILE" ;;
    *) ENV_PATH="$PROJECT_ROOT/$LOCAL_ENV_FILE" ;;
esac

# Load .env variables
if [ -f "$ENV_PATH" ]; then
    echo "--- Loading environment from $ENV_PATH ---"
    dotenv_load "$ENV_PATH"
fi

# Configuration
STACK_NAME="${DEPLOY_TARGET_NAME:-muma}"
STACK_NAME=$(echo "$STACK_NAME" | tr '[:upper:]' '[:lower:]')
SERVICE_NAME="${SERVICE_NAME}"
IMAGE_NAME="${IMAGE_NAME}"

# Parse positional arguments for service name
for arg in "$@"; do
    case $arg in
        --debug|--remote|--semi-remote|--skip-lint|--skip-test) ;;
        *) 
            if [ -z "$SERVICE_NAME" ]; then
                SERVICE_NAME="$arg"
                # Map shorthand names to service names in docker-compose.yml
                if [ "$SERVICE_NAME" == "manager" ]; then SERVICE_NAME="music-manager"; fi
            fi
            ;;
    esac
done
TAG="${TAG:-latest}"
SEARCH_STRING="${SEARCH_STRING:-muma/muma}"
LOCAL_COMPOSE_FILE="${LOCAL_COMPOSE_FILE:-docker/docker-compose.yml}"

# 1. Trigger Portainer Webhook if configured
if [ -n "${PORTAINER_WEBHOOK_URL}" ]; then
    echo "--- Triggering Portainer Webhook for: $STACK_NAME ---"
    if command -v curl >/dev/null 2>&1; then
        STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${PORTAINER_WEBHOOK_URL}")
        if [ "$STATUS_CODE" -ge 200 ] && [ "$STATUS_CODE" -lt 300 ]; then
            echo "--- Webhook triggered successfully (Status: $STATUS_CODE) ---"
        elif [ "$STATUS_CODE" -eq 404 ]; then
            echo "Error: Portainer Webhook returned 404 Not Found."
            echo "Note: Stack Webhooks are a Business Edition feature."
            exit 1
        else
            echo "Error: Portainer Webhook failed with status code $STATUS_CODE"
            exit 1
        fi
    else
        echo "Error: curl not found. Cannot trigger Portainer Webhook."
        exit 1
    fi
fi

# 2. Remote Deployment via SSH if configured
if [ -n "${REMOTE_HOST}" ] && [ -n "${REMOTE_USER}" ]; then
    echo "--- Starting remote deployment for stack: $STACK_NAME on $REMOTE_HOST ---"
    
    # Discovery command to be run on remote hosts
    DISCOVERY_CMD="
        ACTUAL_COMPOSE_FILE=\"\"
        if [ -n \"$STACK_NAME\" ]; then
            CONTAINER_ID=\$(docker ps -q --filter \"label=com.docker.compose.project=$STACK_NAME\" | head -n 1)
            if [ -n \"\$CONTAINER_ID\" ]; then
                ACTUAL_COMPOSE_FILE=\$(docker inspect \"\$CONTAINER_ID\" --format '{{ index .Config.Labels \"com.docker.compose.project.config_files\" }}' 2>/dev/null | cut -d, -f1)
            fi
        fi
        if ([ -z \"\$ACTUAL_COMPOSE_FILE\" ] || [ ! -f \"\$ACTUAL_COMPOSE_FILE\" ]) && [ -n \"$SERVICE_NAME\" ]; then
            ACTUAL_COMPOSE_FILE=\$(docker inspect \"$SERVICE_NAME\" --format '{{ index .Config.Labels \"com.docker.compose.project.config_files\" }}' 2>/dev/null | cut -d, -f1)
        fi
        if ([ -z \"\$ACTUAL_COMPOSE_FILE\" ] || [ ! -f \"\$ACTUAL_COMPOSE_FILE\" ]) && [ -n \"$REMOTE_STACK_PATH\" ]; then
            if [ -f \"\$REMOTE_STACK_PATH\" ]; then ACTUAL_COMPOSE_FILE=\"\$REMOTE_STACK_PATH\"; fi
        fi
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
    
    # Use local compose file if provided (Source of truth)
    if [ -f "$PROJECT_ROOT/$LOCAL_COMPOSE_FILE" ]; then
        echo "Using local configuration file: $LOCAL_COMPOSE_FILE"
        COMPOSE_CONTENT=$(expand -t 4 "$PROJECT_ROOT/$LOCAL_COMPOSE_FILE")
    else
        echo "Local compose file not found, attempting discovery on remote..."
        RESULT=$(run_ssh "$REMOTE_HOST" "$REMOTE_USER" "$REMOTE_PASS" "REMOTE_STACK_PATH='$REMOTE_STACK_PATH' $DISCOVERY_CMD" 2>/dev/null || true)
        if echo "$RESULT" | grep -q "^FOUND_FILE:"; then
            COMPOSE_CONTENT=$(echo "$RESULT" | sed -n '/^FOUND_FILE:/!p' | expand -t 4)
            echo "Found existing configuration on $REMOTE_HOST"
        fi
    fi

    if [ -z "$COMPOSE_CONTENT" ]; then
        echo "Error: No docker-compose configuration found."
        exit 1
    fi

    # The compose file is no secret (it is the tracked file), so it may ride on
    # the command line; the env file may not.
    B64_DATA=$(echo "$COMPOSE_CONTENT" | base64 -w 0)
    SEND_ENV=0
    if [ -f "$ENV_PATH" ]; then
        SEND_ENV=1
    fi

    # Deployment logic
    #
    # Everything lands in a root-only directory under the remote user's home,
    # not in world-writable /tmp: a file another account can pre-create or
    # swap there is a file root would hand to compose. The compose file stays
    # (it holds no secrets, and the container labels point at it); the env file
    # is written into a per-run directory that the EXIT trap removes as soon as
    # compose is done with it. compose only reads --env-file while it parses the
    # project, so nothing needs it afterwards. A run killed before its trap
    # fired is cleaned up by the next one (the rm of run.*).
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

        ENV_ARG=\"\"
        if [ \"$SEND_ENV\" = 1 ]; then
            FINAL_ENV_FILE=\"\$RUN_DIR/.env\"
            cat > \"\$FINAL_ENV_FILE\"
            ENV_ARG=\"--env-file \$FINAL_ENV_FILE\"
        fi

        # No lookup in /tmp: this runs as root, and an executable any local
        # account could drop into /tmp would be run as root on the next deploy.
        if docker compose version >/dev/null 2>&1; then
            DOCKER_CMD=\"docker compose \$ENV_ARG -f \$FINAL_COMPOSE_FILE -p $STACK_NAME\"
        elif command -v docker-compose >/dev/null 2>&1; then
            DOCKER_CMD=\"docker-compose \$ENV_ARG -f \$FINAL_COMPOSE_FILE -p $STACK_NAME\"
        else
            echo \"Error: No docker-compose command found on remote.\"
            exit 1
        fi
        
        echo \"Updating stack '$STACK_NAME'...\"
        
        \$DOCKER_CMD pull

        # A container whose image has since been pruned off the host cannot be
        # recreated in place: compose stops and asks \"Continue with the new image?
        # [yN]\", which has no answer over a non-interactive ssh, so the deploy dies
        # having already recreated half the stack. Drop those containers here and
        # let 'up -d' build them fresh from the image we just pulled.
        for CID in \$(docker ps -aq --filter \"label=com.docker.compose.project=$STACK_NAME\"); do
            CIMG=\$(docker inspect --format '{{.Image}}' \"\$CID\" 2>/dev/null || echo '')
            if [ -n \"\$CIMG\" ] && ! docker image inspect \"\$CIMG\" >/dev/null 2>&1; then
                echo \"Container \$(docker inspect --format '{{.Name}}' \"\$CID\" 2>/dev/null) references a missing image, removing it so it can be recreated.\"
                docker rm -f \"\$CID\" >/dev/null
            fi
        done

        if [ -n \"$SERVICE_NAME\" ] && \$DOCKER_CMD config --services | grep -q \"^$SERVICE_NAME\$\"; then
            echo \"Updating service: $SERVICE_NAME\"
            \$DOCKER_CMD up -d --force-recreate --remove-orphans $SERVICE_NAME
        else
            echo \"Updating full stack...\"
            \$DOCKER_CMD up -d --force-recreate --remove-orphans
        fi
    "

    if [ "$SEND_ENV" = 1 ]; then
        run_ssh "$REMOTE_HOST" "$REMOTE_USER" "$REMOTE_PASS" "$DEPLOY_CMD" < "$ENV_PATH"
    else
        run_ssh "$REMOTE_HOST" "$REMOTE_USER" "$REMOTE_PASS" "$DEPLOY_CMD" < /dev/null
    fi

    # 3. Database Migrations
    # Glob is migrate_*.sql, matching the !migrate_*.sql exception in .gitignore
    # exactly: one naming rule decides both what gets committed and what gets
    # applied, so a migration can no longer be silently skipped by one of the two
    # (see docs/bug-reports/021-genre-migration-never-shipped.md). Every match
    # runs on every deploy, so migrations must be re-runnable.
    for sql_file in "$PROJECT_ROOT"/migrate_*.sql; do
        if [ -f "$sql_file" ]; then
            fname=$(basename "$sql_file")
            echo "--- Executing database migration: $fname ---"

            MIGRATION_USER="$DB_USER"
            MIGRATION_PASS="$DB_PASS"
            if [ -n "$MYSQL_ROOT_PASSWORD" ]; then
                MIGRATION_USER="root"
                MIGRATION_PASS="$MYSQL_ROOT_PASSWORD"
            fi

            # stdin carries the password on its first line and the SQL after
            # it. The remote shell reads the first line into MYSQL_PWD (the
            # mariadb client's password variable) and hands the rest of stdin
            # straight to the client; `docker exec -e MYSQL_PWD` without a value
            # copies it from the environment, so the password is on no command
            # line -- not the ssh one here, not docker's or mariadb's there --
            # and no SQL file is left in /tmp either. Same idea as the
            # --defaults-extra-file in tools/db_backup.py.
            #
            # The migration's exit status is the remote command's status,
            # because docker exec is its last command. It used to be masked by
            # a trailing "rm" and the deploy reported success while the schema
            # had aborted halfway. See
            # docs/bug-reports/021-genre-migration-never-shipped.md.
            #
            # `mariadb`, not `mysql`: MariaDB renamed the client in 10.5 and
            # dropped the old name in 12, where this would exit 127 and fail
            # every migration on a server that is otherwise perfectly healthy.
            REMOTE_MIGRATE_CMD="
                IFS= read -r MYSQL_PWD
                export MYSQL_PWD
                docker exec -i -e MYSQL_PWD music-management-db-1 mariadb -u \"$MIGRATION_USER\" \"$DB_DB\"
            "
            { printf '%s\n' "$MIGRATION_PASS"; cat "$sql_file"; } \
                | run_ssh "$REMOTE_HOST" "$REMOTE_USER" "$REMOTE_PASS" "$REMOTE_MIGRATE_CMD"
        fi
    done
    
    echo "--- Remote deployment completed successfully ---"
else
    echo "Error: Remote deployment skipped. No PORTAINER_WEBHOOK_URL, REMOTE_HOST, or SSH targets configured in .env."
    echo "To deploy locally, use 'docker compose up -d' or configure your remote target."
    exit 1
fi
