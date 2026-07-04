#!/bin/bash
set -e

# Remote Deployment / Auto Upgrade
cd "$(dirname "$0")"
if [ -f .env ]; then
    # Load .env variables
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ ! "$line" =~ ^# && -n "$line" ]]; then
            export "$line"
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
    echo "--- Starting remote update on ${REMOTE_HOST} for: $TARGET ---"
    
    REMOTE_COMMAND="
    set -e
    # Try to find docker-compose file
    if [ -f \"${DOCKER_COMPOSE_FILE}\" ]; then
        echo \"Updating stack '$TARGET' via docker-compose using ${DOCKER_COMPOSE_FILE}...\"
        docker-compose -f \"${DOCKER_COMPOSE_FILE}\" pull || docker compose -f \"${DOCKER_COMPOSE_FILE}\" pull
        docker-compose -f \"${DOCKER_COMPOSE_FILE}\" up -d || docker compose -f \"${DOCKER_COMPOSE_FILE}\" up -d
    elif [ -d \"${DOCKER_COMPOSE_FILE}\" ] && [ -f \"${DOCKER_COMPOSE_FILE}/docker-compose.yml\" ]; then
        echo \"Updating stack '$TARGET' in directory ${DOCKER_COMPOSE_FILE}...\"
        cd \"${DOCKER_COMPOSE_FILE}\"
        docker-compose pull || docker compose pull
        docker-compose up -d || docker compose up -d
    else
        echo \"Warning: Docker compose configuration not found at '${DOCKER_COMPOSE_FILE}' on remote host.\"
        echo \"Updating individual containers for '$TARGET':\"
        
        # Project-specific individual pulls/runs
        docker pull ${DOCKER_USER}/${IMAGE_ML}:latest
        docker pull ${DOCKER_USER}/${IMAGE_TOOLS}:latest
        docker pull ${DOCKER_USER}/${IMAGE_APP}:latest
        docker pull ${DOCKER_USER}/${IMAGE_MANAGEMENT}:latest
        
        # Note: Individual run commands would go here if needed
    fi
    "
    
    if [ -z "${REMOTE_PASS}" ]; then
        echo "REMOTE_PASS not set. SSH may ask for password."
        ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" "${REMOTE_COMMAND}"
    elif command -v sshpass >/dev/null 2>&1; then
        sshpass -p "${REMOTE_PASS}" ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" "${REMOTE_COMMAND}"
    else
        echo "Error: sshpass not found. Install it or unset REMOTE_PASS and enter password manually."
        exit 1
    fi
    
    echo "--- Remote update completed ---"
else
    echo "Remote deployment skipped: Neither PORTAINER_WEBHOOK_URL nor REMOTE_HOST/REMOTE_USER are set in .env"
fi
