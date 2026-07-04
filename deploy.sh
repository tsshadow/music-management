#!/bin/bash
set -e

# Remote Deployment / Auto Upgrade
if [ -f .env ]; then
    # Load .env variables
    export $(grep -v '^#' .env | xargs)
fi

if [ -n "${PORTAINER_WEBHOOK_URL}" ]; then
    TARGET="${DEPLOY_TARGET_NAME:-Portainer Stack}"
    echo "--- Triggering Portainer Webhook for: $TARGET ---"
    if command -v curl >/dev/null 2>&1; then
        curl -X POST "${PORTAINER_WEBHOOK_URL}"
        echo -e "\n--- Webhook triggered for $TARGET ---"
    else
        echo "Error: curl not found. Cannot trigger Portainer Webhook."
        exit 1
    fi
elif [ -n "${REMOTE_HOST}" ] && [ -n "${REMOTE_USER}" ]; then
    TARGET="${DEPLOY_TARGET_NAME:-Music Management Stack}"
    echo "--- Starting remote update on ${REMOTE_HOST} for: $TARGET ---"
    
    # If REMOTE_DOCKER_COMPOSE_PATH is not set, try a default or warn
    DOCKER_COMPOSE_FILE="${REMOTE_DOCKER_COMPOSE_PATH:-docker-compose.yml}"
    
    REMOTE_COMMAND="
    set -e
    if [ -f \"${DOCKER_COMPOSE_FILE}\" ]; then
        echo \"Updating stack '$TARGET' via docker-compose using ${DOCKER_COMPOSE_FILE}...\"
        docker-compose -f \"${DOCKER_COMPOSE_FILE}\" pull
        docker-compose -f \"${DOCKER_COMPOSE_FILE}\" up -d
    else
        echo \"Warning: ${DOCKER_COMPOSE_FILE} not found on remote host.\"
        echo \"Updating individual containers for '$TARGET':\"
        echo \"  - tsshadow/music-management-ml:latest\"
        echo \"  - tsshadow/music-management-tools:latest\"
        echo \"  - tsshadow/music-management:latest\"
        
        docker pull tsshadow/music-management-ml:latest
        docker pull tsshadow/music-management-tools:latest
        docker pull tsshadow/music-management:latest
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
