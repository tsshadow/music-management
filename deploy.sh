#!/bin/bash
set -e

# Remote Deployment / Auto Upgrade
cd "$(dirname "$0")"
if [ -f .env ]; then
    # Load .env variables
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Strip trailing comments and whitespace
        clean_line=$(echo "$line" | sed 's/[[:space:]]*#.*$//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [[ -n "$clean_line" && ! "$clean_line" =~ ^# ]]; then
            export "$clean_line"
        fi
    done < .env
fi

# Configuration
TARGET="${DEPLOY_TARGET_NAME}"
DOCKER_COMPOSE_FILE="${REMOTE_STACK_PATH}"

if [ -n "${PORTAINER_WEBHOOK_URL}" ]; then
    echo "--- Triggering Portainer Webhook for: $TARGET ---"
    if command -v curl >/dev/null 2>&1; then
        STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${PORTAINER_WEBHOOK_URL}")
        if [ "$STATUS_CODE" -ge 200 ] && [ "$STATUS_CODE" -lt 300 ]; then
            echo "--- Webhook triggered successfully for $TARGET (Status: $STATUS_CODE) ---"
        elif [ "$STATUS_CODE" -eq 404 ]; then
            echo "Error: Portainer Webhook returned 404 Not Found."
            echo "Note: Stack Webhooks are a Business Edition feature."
            if [[ "${PORTAINER_WEBHOOK_URL}" == *"/stacks/"* ]]; then
                echo "HINT: You are using a Stack Webhook URL, which requires Portainer Business Edition."
                echo "If you have Community Edition, you can use 'Service Webhooks' (under each service) or the SSH method."
            fi
            if [[ "${PORTAINER_WEBHOOK_URL}" == *"ptr_"* ]]; then
                echo "HINT: Your URL seems to contain an API Access Token (ptr_...). Webhooks use a different token."
            fi
            exit 1
        else
            echo "Error: Portainer Webhook failed with status code $STATUS_CODE"
            exit 1
        fi
    else
        echo "Error: curl not found. Cannot trigger Portainer Webhook."
        exit 1
    fi
elif [ -n "${REMOTE_HOST}" ] && [ -n "${REMOTE_USER}" ]; then
    echo "--- Starting remote deployment for stack: $TARGET ---"
    
    # Use the generalized deployment script
    export LOCAL_COMPOSE_FILE="docker-compose.yml"
    export LOCAL_ENV_FILE=".env"
    export SEARCH_STRING="tsshadow/music-management"
    
    ./scripts/deploy-stack.sh "$@"
    
    # Run database migrations if any
    for sql_file in migrate_v*.sql; do
        if [ -f "$sql_file" ]; then
            echo "--- Executing database migration: $sql_file ---"
            B64_SQL=$(base64 -w 0 "$sql_file")
            # Use docker exec on the db container to run the SQL
            # We assume the container name from docker-compose.yml: music-management-db-1
            # and credentials from .env
            # Use root if available, otherwise fallback to DB_USER for migrations
            MIGRATION_USER="$DB_USER"
            MIGRATION_PASS="$DB_PASS"
            if [ -n "$MYSQL_ROOT_PASSWORD" ]; then
                MIGRATION_USER="root"
                MIGRATION_PASS="$MYSQL_ROOT_PASSWORD"
            fi

            REMOTE_CMD="
                echo '$B64_SQL' | base64 -d > /tmp/migration.sql
                docker exec -i music-management-db-1 mysql -u \"$MIGRATION_USER\" -p\"$MIGRATION_PASS\" \"$DB_DB\" < /tmp/migration.sql
                rm /tmp/migration.sql
            "
            if [ -z "$REMOTE_PASS" ]; then
                ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" "${REMOTE_CMD}"
            elif command -v sshpass >/dev/null 2>&1; then
                sshpass -p "${REMOTE_PASS}" ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" "${REMOTE_CMD}"
            fi
        fi
    done
    
    echo "--- Deployment completed successfully ---"
else
    echo "Remote deployment skipped: Neither PORTAINER_WEBHOOK_URL nor REMOTE_HOST/REMOTE_USER are set in .env"
fi
