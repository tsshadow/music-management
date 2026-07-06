#!/bin/bash
# Comprehensive Docker Stack Deployment Script
# Handles: Webhooks, Remote SSH updates, and Database Migrations.

set -e

# Helper function to run SSH command
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
        sshpass -p "${pass}" ssh -o StrictHostKeyChecking=no "${user}@${host}" "${cmd}"
    else
        echo "Error: sshpass not found. Install it or unset password variable."
        exit 1
    fi
}

# Ensure we are in the project root if possible, or handle relative paths
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load .env variables
if [ -f "$PROJECT_ROOT/.env" ]; then
    echo "--- Loading environment from $PROJECT_ROOT/.env ---"
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Strip trailing comments and whitespace
        clean_line=$(echo "$line" | sed 's/[[:space:]]*#.*$//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [[ -n "$clean_line" && ! "$clean_line" =~ ^# ]]; then
            export "$clean_line"
        fi
    done < "$PROJECT_ROOT/.env"
fi

# Configuration
STACK_NAME="${DEPLOY_TARGET_NAME:-muma}"
STACK_NAME=$(echo "$STACK_NAME" | tr '[:upper:]' '[:lower:]')
SERVICE_NAME="${SERVICE_NAME}"
IMAGE_NAME="${IMAGE_NAME}"

# Parse positional arguments for service name
for arg in "$@"; do
    case $arg in
        --debug|--remote|--semi-remote) ;;
        *) 
            if [ -z "$SERVICE_NAME" ]; then
                SERVICE_NAME="$arg"
                # Map shorthand names to service names in docker-compose.yml
                if [ "$SERVICE_NAME" == "manager" ]; then SERVICE_NAME="music-manager"; fi
                if [ "$SERVICE_NAME" == "app" ]; then SERVICE_NAME="importer_api"; fi
            fi
            ;;
    esac
done
TAG="${TAG:-latest}"
SEARCH_STRING="${SEARCH_STRING:-tsshadow/muma}"
LOCAL_COMPOSE_FILE="${LOCAL_COMPOSE_FILE:-docker-compose.yml}"
LOCAL_ENV_FILE="${LOCAL_ENV_FILE:-.env}"

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

    # Deployment logic
    DEPLOY_CMD="
        set -e
        FINAL_COMPOSE_FILE=\"/tmp/docker-compose.$STACK_NAME.yml\"
        echo \"\$BASE64_COMPOSE\" | base64 -d > \"\$FINAL_COMPOSE_FILE\"
        
        ENV_ARG=\"\"
        if [ -n \"\$BASE64_ENV\" ]; then
            FINAL_ENV_FILE=\"/tmp/.env.$STACK_NAME\"
            echo \"\$BASE64_ENV\" | base64 -d > \"\$FINAL_ENV_FILE\"
            ENV_ARG=\"--env-file \$FINAL_ENV_FILE\"
        fi

        if [ -x /tmp/docker-compose-v2 ]; then
            DOCKER_CMD=\"/tmp/docker-compose-v2 \$ENV_ARG -f \$FINAL_COMPOSE_FILE -p $STACK_NAME\"
        elif docker compose version >/dev/null 2>&1; then
            DOCKER_CMD=\"docker compose \$ENV_ARG -f \$FINAL_COMPOSE_FILE -p $STACK_NAME\"
        elif command -v docker-compose >/dev/null 2>&1; then
            DOCKER_CMD=\"docker-compose \$ENV_ARG -f \$FINAL_COMPOSE_FILE -p $STACK_NAME\"
        else
            echo \"Error: No docker-compose command found on remote.\"
            exit 1
        fi
        
        echo \"Updating stack '$STACK_NAME'...\"
        
        \$DOCKER_CMD pull
        
        if [ -n \"$SERVICE_NAME\" ] && \$DOCKER_CMD config --services | grep -q \"^$SERVICE_NAME\$\"; then
            echo \"Updating service: $SERVICE_NAME\"
            \$DOCKER_CMD up -d --force-recreate --remove-orphans $SERVICE_NAME
        else
            echo \"Updating full stack...\"
            \$DOCKER_CMD up -d --force-recreate --remove-orphans
        fi
    "

    B64_DATA=$(echo "$COMPOSE_CONTENT" | base64 -w 0)
    B64_ENV=""
    if [ -f "$PROJECT_ROOT/$LOCAL_ENV_FILE" ]; then
        B64_ENV=$(base64 -w 0 "$PROJECT_ROOT/$LOCAL_ENV_FILE")
    fi
    
    run_ssh "$REMOTE_HOST" "$REMOTE_USER" "$REMOTE_PASS" "BASE64_COMPOSE='$B64_DATA' BASE64_ENV='$B64_ENV' $DEPLOY_CMD"

    # 3. Database Migrations
    for sql_file in "$PROJECT_ROOT"/migrate_v*.sql; do
        if [ -f "$sql_file" ]; then
            fname=$(basename "$sql_file")
            echo "--- Executing database migration: $fname ---"
            B64_SQL=$(base64 -w 0 "$sql_file")
            
            MIGRATION_USER="$DB_USER"
            MIGRATION_PASS="$DB_PASS"
            if [ -n "$MYSQL_ROOT_PASSWORD" ]; then
                MIGRATION_USER="root"
                MIGRATION_PASS="$MYSQL_ROOT_PASSWORD"
            fi

            REMOTE_MIGRATE_CMD="
                echo '$B64_SQL' | base64 -d > /tmp/migration.sql
                docker exec -i music-management-db-1 mysql -u \"$MIGRATION_USER\" -p\"$MIGRATION_PASS\" \"$DB_DB\" < /tmp/migration.sql
                rm /tmp/migration.sql
            "
            run_ssh "$REMOTE_HOST" "$REMOTE_USER" "$REMOTE_PASS" "$REMOTE_MIGRATE_CMD"
        fi
    done
    
    echo "--- Remote deployment completed successfully ---"
else
    echo "Error: Remote deployment skipped. No PORTAINER_WEBHOOK_URL, REMOTE_HOST, or SSH targets configured in .env."
    echo "To deploy locally, use 'docker compose up -d' or configure your remote target."
    exit 1
fi
