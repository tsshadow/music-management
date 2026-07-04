#!/bin/bash
set -e

cd "$(dirname "$(readlink -f "$0")")/.."

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

# Determine mode (debug is default)
MODE="${1:-${BUILD_MODE:-debug}}"

# Load explicit overrides from environment if provided, otherwise sensible defaults based on MODE
export DEPLOY_TARGET_NAME="${DEPLOY_TARGET_NAME:-lms}"
export IMAGE_NAME="${IMAGE_NAME:-muma/lms}"

# Tag logic
if [ -z "$TAG" ] || [ "$TAG" == "latest" ] || [ "$TAG" == "stable" ]; then
    if [ "$MODE" == "release" ]; then
        TAG="stable"
    else
        TAG="latest"
    fi
fi

# Service name selection and Tag assignment based on mode
if [ "$MODE" == "release" ]; then
    SERVICE_NAME="lms"
    export LMS_TAG="$TAG"
    echo "Release mode: deploying service '$SERVICE_NAME' with tag '$LMS_TAG'"
else
    SERVICE_NAME="lms_alpha"
    export LMS_ALPHA_TAG="$TAG"
    echo "Debug mode: deploying service '$SERVICE_NAME' with tag '$LMS_ALPHA_TAG'"
fi
export SERVICE_NAME

TARGET=$(echo "${DEPLOY_TARGET_NAME}" | tr '[:upper:]' '[:lower:]')
DOCKER_COMPOSE_FILE="${REMOTE_STACK_PATH}"


# Webhook method
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
    exit 0
fi

# SSH method
if [ -n "${REMOTE_HOST}" ] && [ -n "${REMOTE_USER}" ]; then
    echo "--- Starting remote deployment for stack: $TARGET ---"
    
    # Use the generalized deployment script
    export LOCAL_COMPOSE_FILE="docker-compose.yml"
    export LOCAL_ENV_FILE=".env"
    export SEARCH_STRING="muma/lms"
    # Pass mode-specific tags through EXTRA_VARS
    export EXTRA_VARS="LMS_TAG=$LMS_TAG LMS_ALPHA_TAG=$LMS_ALPHA_TAG"
    
    ./scripts/deploy-stack.sh
    
    echo "--- Deployment completed successfully ---"
else
    echo "Error: REMOTE_HOST and REMOTE_USER must be set in .env for SSH deployment."
    exit 1
fi