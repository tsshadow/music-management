#!/bin/bash

# MuMa Database Backup Script
# Creates a SQL dump of the MariaDB database and stores it in /muma/backups

set -e

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/muma/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Determine project root (one level up from tools/)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load .env if it exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Strip trailing comments and whitespace
        clean_line=$(echo "$line" | sed 's/[[:space:]]*#.*$//' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [[ -n "$clean_line" && ! "$clean_line" =~ ^# ]]; then
            # Use export for the cleaned line, handling possible spaces
            export "$clean_line"
        fi
    done < "$PROJECT_ROOT/.env"
fi

# Fallback values
DB_USER=${DB_USER:-"music-management"}
DB_NAME=${DB_DB:-"music-management"}
ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD}

if [ -z "$ROOT_PASSWORD" ]; then
    echo "Error: MYSQL_ROOT_PASSWORD not found in environment or .env file."
    exit 1
fi

# Ensure backup directory exists
if [ ! -d "$BACKUP_DIR" ]; then
    echo "Creating backup directory: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
fi

BACKUP_FILE="${BACKUP_DIR}/muma_backup_${TIMESTAMP}.sql"

echo "--- Starting Database Backup (${TIMESTAMP}) ---"

# Check if running inside a container or on host
if [ -f /.dockerenv ]; then
    # Inside container, try to connect to the 'db' host
    echo "Running inside container, connecting to host: ${DB_HOST:-db}"
    mysqldump -h "${DB_HOST:-db}" -u root --password="${ROOT_PASSWORD}" "${DB_NAME}" > "$BACKUP_FILE"
else
    # On host, try docker exec first as it's the most reliable for local docker setups
    CONTAINER_NAME="music-management-db-1"
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "Found running container: ${CONTAINER_NAME}. Using docker exec..."
        docker exec "${CONTAINER_NAME}" /usr/bin/mysqldump --single-transaction --quick -u root --password="${ROOT_PASSWORD}" "${DB_NAME}" > "$BACKUP_FILE"
    else
        echo "Container ${CONTAINER_NAME} not found. Attempting direct mysqldump..."
        # If DB_HOST is 'db', it might not work from host unless 'db' is in /etc/hosts
        HOST_TARGET="${DB_HOST:-localhost}"
        if [ "$HOST_TARGET" == "db" ]; then
            HOST_TARGET="localhost"
        fi
        mysqldump -h "${HOST_TARGET}" -u root --password="${ROOT_PASSWORD}" "${DB_NAME}" > "$BACKUP_FILE"
    fi
fi

# Check if file was created and is not empty
if [ -s "$BACKUP_FILE" ]; then
    # Compress the backup
    gzip "$BACKUP_FILE"
    FINAL_FILE="${BACKUP_FILE}.gz"

    echo "--- Backup Completed Successfully ---"
    echo "Location: ${FINAL_FILE}"
    echo "Size: $(du -h "${FINAL_FILE}" | cut -f1)"
else
    echo "Error: Backup file is empty or was not created."
    exit 1
fi
