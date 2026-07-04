#!/bin/bash
set -e

# Remote Deployment / Auto Upgrade
cd "$(dirname "$0")"
if [ -f .env ]; then
    # Load .env variables
    export $(grep -v '^#' .env | xargs)
fi

# Configuration
TARGET="${DEPLOY_TARGET_NAME}"
DOCKER_COMPOSE_FILE="${REMOTE_STACK_PATH}"

if [ -n "${PORTAINER_WEBHOOK_URL}" ]; then
    echo "--- Triggering Portainer Webhook for: $TARGET ---"
    if command -v curl >/dev/null 2>&1; then
        curl -X POST "${PORTAINER_WEBHOOK_URL}"
        echo -e "\n--- Webhook triggered for $TARGET ---"
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
        docker pull tsshadow/music-management-ml:latest
        docker pull tsshadow/music-management-tools:latest
        docker pull tsshadow/music-management:latest
        
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
