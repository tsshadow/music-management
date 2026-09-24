#!/bin/bash
set -e

cd "$(dirname "$(readlink -f "$0")")/.."

# shellcheck source=scripts/lib/dotenv.sh
. ../../scripts/lib/dotenv.sh

# Load .env variables; values already in the environment win. The shared parser
# keeps a `#` inside a value (a password, say), where the old sed one-liner cut
# it off -- see docs/bug-reports/038-deploy-puts-every-prod-secret-on-the-command-line.md.
if [ -f .env ]; then
    dotenv_load .env --keep-existing
fi

# Determine mode (debug is default)
MODE="${1:-${BUILD_MODE:-debug}}"

# Load explicit overrides from environment if provided, otherwise sensible defaults based on MODE
export DEPLOY_TARGET_NAME="${DEPLOY_TARGET_NAME}"
export IMAGE_NAME="${IMAGE_NAME}"

# Tag logic
if [ -z "$TAG" ] || [ "$TAG" == "latest" ] || [ "$TAG" == "stable" ] || [ "$TAG" == "alpha" ]; then
    if [ "$MODE" == "release" ]; then
        TAG="latest"
    else
        TAG="alpha"
    fi
fi

# Service name selection and Tag assignment based on mode
# NOTE: since production-lms-consolidation, docker-compose.yml only defines a
# single "lms" service (the old "lms_alpha" service was removed). Debug-mode
# deploys still build/push an "alpha"-tagged image, but there is no separate
# alpha container left to deploy it to.
if [ "$MODE" == "release" ]; then
    export LMS_TAG="$TAG"
    echo "Release mode: using tag '$LMS_TAG' for lms"
else
    echo "Debug mode: image tagged '$TAG' was pushed, but is not deployed (no lms_alpha service anymore)."
fi

# Ensure the tag and image name are passed to the remote host
export EXTRA_VARS="LMS_TAG=$LMS_TAG IMAGE_NAME=$IMAGE_NAME MUSIC_PATH=$MUSIC_PATH DOCKER_DATA_PATH=$DOCKER_DATA_PATH"

# We don't restrict to a single service name by default,
# to ensure the whole stack (just "lms" now) is recreated if needed.
unset SERVICE_NAME

TARGET=$(echo "${DEPLOY_TARGET_NAME}" | tr '[:upper:]' '[:lower:]')


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
    
    ./scripts/deploy-stack.sh
    
    echo "--- Deployment completed successfully ---"
else
    echo "Error: REMOTE_HOST and REMOTE_USER must be set in .env for SSH deployment."
    exit 1
fi