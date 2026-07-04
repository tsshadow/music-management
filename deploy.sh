#!/bin/bash
set -e

cd "$(dirname "$0")"

# Load .env variables, stripping comments and extra whitespace
if [ -f .env ]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Strip trailing comments and whitespace
        clean_line=$(echo "$line" | sed 's/[[:space:]]*#.*$//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [[ -n "$clean_line" && ! "$clean_line" =~ ^# ]]; then
            export "$clean_line"
        fi
    done < .env
fi

# Configuration
IMAGE_NAME="${IMAGE_NAME:-muma/lms}"
SERVICE_NAME="${SERVICE_NAME:-lms}"
TAG="${TAG}"

# Default tag logic based on service name if using generic tags
if [ -z "$TAG" ] || [ "$TAG" == "latest" ] || [ "$TAG" == "stable" ]; then
    if [ "$SERVICE_NAME" == "lms" ]; then
        TAG="stable"
    else
        TAG="latest"
    fi
fi

TARGET=$(echo "${DEPLOY_TARGET_NAME}" | tr '[:upper:]' '[:lower:]')
DOCKER_COMPOSE_FILE="${REMOTE_STACK_PATH}"


# Webhook method
if [ -n "${PORTAINER_WEBHOOK_URL}" ]; then
    echo "--- Triggering Portainer Webhook for: $TARGET ---"
    if command -v curl >/dev/null 2>&1; then
        STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${PORTAINER_WEBHOOK_URL}")
        if [ "$STATUS_CODE" -ge 200 ] && [ "$STATUS_CODE" -lt 300 ]; then
            echo "--- Webhook triggered successfully for $TARGET (Status: $STATUS_CODE) ---"
        else
            echo "Error: Portainer Webhook failed with status code $STATUS_CODE"
            exit 1
        fi
    else
        echo "Error: curl not found. Cannot trigger Portainer Webhook."
        exit 1
    fi
    exit 0
fi

# SSH method
if [ -n "${REMOTE_HOST}" ] && [ -n "${REMOTE_USER}" ]; then
    echo "--- Starting remote deployment for stack: $TARGET ---"
    
    # Use the generalized deployment script
    export LOCAL_COMPOSE_FILE="docker-compose.yml"
    export SEARCH_STRING="muma/lms"
    
    ./scripts/deploy-stack.sh
    
    echo "--- Deployment completed successfully ---"
else
    echo "Error: REMOTE_HOST and REMOTE_USER must be set in .env for SSH deployment."
    exit 1
fi