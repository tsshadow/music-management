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

# MariaDB renamed its client binaries in 10.5 (mysqldump -> mariadb-dump) and
# removed the old names entirely in 12. A backup that calls the old name against
# a 12 server does not warn -- it exits 127, "command not found", and the only
# evidence is a zero-byte file. The `-s` check further down catches that, but
# only after the backup did not happen.
#
# Inside the database container the new name is always there, so that call site
# uses it directly. Here the binary comes from whatever client package this host
# or image happens to have, which may still be the old one, so resolve it.
resolve_dump() {
    if command -v mariadb-dump >/dev/null 2>&1; then
        echo mariadb-dump
    elif command -v mysqldump >/dev/null 2>&1; then
        echo mysqldump
    else
        echo "ERROR: neither mariadb-dump nor mysqldump is installed." >&2
        exit 1
    fi
}

# Check if running inside a container or on host
if [ -f /.dockerenv ]; then
    # Inside container, try to connect to the 'db' host
    echo "Running inside container, connecting to host: ${DB_HOST:-db}"
    "$(resolve_dump)" -h "${DB_HOST:-db}" -u root --password="${ROOT_PASSWORD}" "${DB_NAME}" > "$BACKUP_FILE"
else
    # On host, try docker exec first as it's the most reliable for local docker setups
    CONTAINER_NAME="music-management-db-1"
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "Found running container: ${CONTAINER_NAME}. Using docker exec..."
        # Inside the mariadb image: mariadb-dump has existed since 10.5 and is
        # the only name left in 12. No absolute path -- it is on PATH there.
        docker exec "${CONTAINER_NAME}" mariadb-dump --single-transaction --quick -u root --password="${ROOT_PASSWORD}" "${DB_NAME}" > "$BACKUP_FILE"
    else
        echo "Container ${CONTAINER_NAME} not found. Attempting a direct dump..."
        # If DB_HOST is 'db', it might not work from host unless 'db' is in /etc/hosts
        HOST_TARGET="${DB_HOST:-localhost}"
        if [ "$HOST_TARGET" == "db" ]; then
            HOST_TARGET="localhost"
        fi
        "$(resolve_dump)" -h "${HOST_TARGET}" -u root --password="${ROOT_PASSWORD}" "${DB_NAME}" > "$BACKUP_FILE"
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
