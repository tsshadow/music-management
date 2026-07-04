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

# Helper function to run SSH command
run_ssh() {
    local host="$1"
    local user="$2"
    local pass="$3"
    local cmd="$4"
    
    if [ -z "$pass" ]; then
        ssh -o StrictHostKeyChecking=no "${user}@${host}" "${cmd}"
    elif command -v sshpass >/dev/null 2>&1; then
        sshpass -p "${pass}" ssh -o StrictHostKeyChecking=no "${user}@${host}" "${cmd}"
    else
        echo "Error: sshpass not found. Install it or unset REMOTE_PASS."
        exit 1
    fi
}

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
    
    DISCOVERY_CMD="
        ACTUAL_COMPOSE_FILE=\"\"
        # 1. Try to find via running container labels for the target project
        if [ -n \"$TARGET\" ]; then
            CONTAINER_ID=\$(docker ps -q --filter \"label=com.docker.compose.project=$TARGET\" | head -n 1)
            if [ -n \"\$CONTAINER_ID\" ]; then
                ACTUAL_COMPOSE_FILE=\$(docker inspect \"\$CONTAINER_ID\" --format '{{ index .Config.Labels \"com.docker.compose.project.config_files\" }}' 2>/dev/null | cut -d, -f1)
            fi
        fi
        # 2. Try to find via SERVICE_NAME label
        if [ -z \"\$ACTUAL_COMPOSE_FILE\" ] || [ ! -f \"\$ACTUAL_COMPOSE_FILE\" ]; then
            if [ -n \"${SERVICE_NAME}\" ]; then
                ACTUAL_COMPOSE_FILE=\$(docker inspect \"${SERVICE_NAME}\" --format '{{ index .Config.Labels \"com.docker.compose.project.config_files\" }}' 2>/dev/null | cut -d, -f1)
            fi
        fi
        # 3. Fallback to provided path
        if [ -z \"\$ACTUAL_COMPOSE_FILE\" ] || [ ! -f \"\$ACTUAL_COMPOSE_FILE\" ]; then
            if [ -f \"${DOCKER_COMPOSE_FILE}\" ]; then ACTUAL_COMPOSE_FILE=\"${DOCKER_COMPOSE_FILE}\"; fi
        fi
        # 4. Search common paths
        if [ -z \"\$ACTUAL_COMPOSE_FILE\" ] || [ ! -f \"\$ACTUAL_COMPOSE_FILE\" ]; then
            for SEARCH_DIR in /data/compose /var/lib/docker/volumes/*/ _data/compose /var/lib/docker/volumes/portainer_portainer_data/_data/compose; do
                if [ -d \"\$SEARCH_DIR\" ]; then
                    MATCH=\$(grep -rl \"muma/lms\" \"\$SEARCH_DIR\" 2>/dev/null | grep \"docker-compose.yml\" | head -n 1)
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
    SOURCE_HOST=""

    # Try discovery on PORTAINER_HOST
    if [ -n "$PORTAINER_HOST" ]; then
        echo "Checking Portainer host $PORTAINER_HOST for stack template..."
        P_USER="${PORTAINER_HOST_USER:-$REMOTE_USER}"
        P_PASS="${PORTAINER_HOST_PASS:-$REMOTE_PASS}"
        RESULT=$(run_ssh "$PORTAINER_HOST" "$P_USER" "$P_PASS" "$DISCOVERY_CMD" 2>/dev/null || true)
        if echo "$RESULT" | grep -q "^FOUND_FILE:"; then
            COMPOSE_CONTENT=$(echo "$RESULT" | sed -n '/^FOUND_FILE:/!p' | expand -t 4)
            SOURCE_HOST="$PORTAINER_HOST"
            echo "Found template on $PORTAINER_HOST"
        fi
    fi

    # Try discovery on REMOTE_HOST if not found on Portainer host
    if [ -z "$COMPOSE_CONTENT" ]; then
        echo "Checking remote host $REMOTE_HOST for existing configuration..."
        RESULT=$(run_ssh "$REMOTE_HOST" "$REMOTE_USER" "$REMOTE_PASS" "$DISCOVERY_CMD" 2>/dev/null || true)
        if echo "$RESULT" | grep -q "^FOUND_FILE:"; then
            COMPOSE_CONTENT=$(echo "$RESULT" | sed -n '/^FOUND_FILE:/!p' | expand -t 4)
            SOURCE_HOST="$REMOTE_HOST"
            echo "Found existing configuration on $REMOTE_HOST"
        fi
    fi

    # Final deployment logic
    DEPLOY_CMD="
        set -e
        FINAL_COMPOSE_FILE=\"\"
        if [ -n \"\$BASE64_COMPOSE\" ]; then
            FINAL_COMPOSE_FILE=\"/tmp/docker-compose.recreated.yml\"
            echo \"\$BASE64_COMPOSE\" | base64 -d > \"\$FINAL_COMPOSE_FILE\"
            echo \"Using configuration discovered from $SOURCE_HOST\"
        else
            # One last check on remote host if transfer failed
            FINAL_COMPOSE_FILE=\$(docker ps --filter \"label=com.docker.compose.project=$TARGET\" --format '{{.Label \"com.docker.compose.project.config_files\"}}' | cut -d, -f1 | head -n 1)
        fi

        if [ -n \"\$FINAL_COMPOSE_FILE\" ] && [ -f \"\$FINAL_COMPOSE_FILE\" ]; then
            PROJECT_NAME=\$(echo \"$TARGET\" | tr '[:upper:]' '[:lower:]')
            if [ -x /tmp/docker-compose-v2 ]; then
                DOCKER_CMD=\"/tmp/docker-compose-v2 -f \$FINAL_COMPOSE_FILE -p \$PROJECT_NAME\"
            elif docker compose version >/dev/null 2>&1; then
                DOCKER_CMD=\"docker compose -f \$FINAL_COMPOSE_FILE -p \$PROJECT_NAME\"
            elif command -v docker-compose >/dev/null 2>&1; then
                DOCKER_CMD=\"docker-compose -f \$FINAL_COMPOSE_FILE -p \$PROJECT_NAME\"
            else
                echo \"Error: Neither docker compose nor docker-compose found.\"
                exit 1
            fi
            
            echo \"Updating stack via: \$DOCKER_CMD\"
            \$DOCKER_CMD pull
            
            if [ -n \"${SERVICE_NAME}\" ] && \$DOCKER_CMD config --services | grep -q \"^${SERVICE_NAME}\$\"; then
                echo \"Updating service: ${SERVICE_NAME}\"
                \$DOCKER_CMD up -d ${SERVICE_NAME}
            else
                echo \"Updating full stack...\"
                \$DOCKER_CMD up -d
            fi
        else
            echo \"Warning: No compose configuration found. Falling back to individual container update...\"
            docker pull ${IMAGE_NAME}:${TAG}
            docker stop ${SERVICE_NAME} 2>/dev/null || true
            docker rm ${SERVICE_NAME} 2>/dev/null || true
            
            PORT_VAL=${LMS_PORT:-80}
            if [ \"${SERVICE_NAME}\" != \"lms\" ]; then PORT_VAL=${LMS_ALPHA_PORT:-8080}; fi
            
            docker run -d --name ${SERVICE_NAME} \
                --restart unless-stopped \
                -p \${PORT_VAL}:5082 \
                -v ${MUSIC_PATH:-/mnt/music}:/music \
                -v ${DOCKER_DATA_PATH:-/mnt/docker}/${SERVICE_NAME}/usr/local/etc:/usr/local/etc \
                -v ${DOCKER_DATA_PATH:-/mnt/docker}/${SERVICE_NAME}/var/lms:/var/lms \
                --user 0:0 \
                ${IMAGE_NAME}:${TAG}
        fi
    "

    if [ -n "$COMPOSE_CONTENT" ]; then
        B64_DATA=$(echo "$COMPOSE_CONTENT" | base64 -w 0)
        run_ssh "$REMOTE_HOST" "$REMOTE_USER" "$REMOTE_PASS" "BASE64_COMPOSE='$B64_DATA' $DEPLOY_CMD"
    else
        run_ssh "$REMOTE_HOST" "$REMOTE_USER" "$REMOTE_PASS" "$DEPLOY_CMD"
    fi
    
    echo "--- Deployment completed successfully ---"
else
    echo "Error: REMOTE_HOST and REMOTE_USER must be set in .env for SSH deployment."
    exit 1
fi