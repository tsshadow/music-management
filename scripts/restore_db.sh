#!/bin/bash
# Restore a backup written by tools/db_backup.py into a database you name.
#
# The target is a required argument and never defaults. The dumps carry no
# CREATE DATABASE or USE statement precisely so that this script decides where
# the data lands -- restoring over production by forgetting a flag is not a
# mistake this should let you make.
#
# Usage:
#   scripts/restore_db.sh <dump.sql.gz> <target-database> [--force]
#
# Restoring over an existing, non-empty database needs --force.
set -euo pipefail

usage() {
    echo "usage: $0 <dump.sql.gz> <target-database> [--force]" >&2
    exit 2
}

DUMP="${1:-}"
TARGET="${2:-}"
FORCE="${3:-}"
[ -n "$DUMP" ] && [ -n "$TARGET" ] || usage
[ -f "$DUMP" ] || { echo "no such dump: $DUMP" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck disable=SC1091
[ -f "$PROJECT_ROOT/.env" ] && set -a && . "$PROJECT_ROOT/.env" && set +a

DB_CONTAINER="${DB_CONTAINER:-music-management-db-1}"
SOURCE_DB="${DB_DB:-music-management}"

if [ "$TARGET" = "$SOURCE_DB" ] && [ "$FORCE" != "--force" ]; then
    echo "refusing to restore over ${TARGET}: it is DB_DB. Pass --force if you mean it." >&2
    exit 1
fi

# Integrity before anything is touched: an unreadable dump should not be
# discovered halfway through overwriting a database.
echo "--- checking ${DUMP} ---"
gzip -t "$DUMP" || { echo "dump does not decompress" >&2; exit 1; }
if ! zcat "$DUMP" | tail -c 4096 | grep -q -- '-- Dump completed'; then
    echo "dump has no '-- Dump completed' trailer; it is truncated" >&2
    exit 1
fi

# The root password is read from the container's own environment and handed to the
# client as MYSQL_PWD, never as -p<password>: a command line inside a container is
# as readable through `ps` on the host as any other. MYSQL_PWD is set in the shell
# inside the container, so the value never crosses the docker command line either.
# shellcheck disable=SC2016 # expanded by the shell inside the container, on purpose
IN_CONTAINER_CLIENT='MYSQL_PWD="${MARIADB_ROOT_PASSWORD:-$MYSQL_ROOT_PASSWORD}"; export MYSQL_PWD; exec mariadb -u root "$@"'

run_sql() {
    docker exec -i "$DB_CONTAINER" sh -c "$IN_CONTAINER_CLIENT" mariadb "$@"
}

EXISTING=$(run_sql <<SQL
SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '${TARGET}';
SQL
)
EXISTING=$(echo "$EXISTING" | tail -1)
if [ "${EXISTING:-0}" -gt 0 ] && [ "$FORCE" != "--force" ]; then
    echo "${TARGET} already holds ${EXISTING} tables. Pass --force to restore over it." >&2
    exit 1
fi

echo "--- restoring ${DUMP} into ${TARGET} ---"
run_sql <<SQL
CREATE DATABASE IF NOT EXISTS \`${TARGET}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
SQL

# The collation is named rather than left to the server default on purpose:
# MariaDB 11.5 changed that default to utf8mb4_uca1400_ai_ci, and a restored
# database whose default disagrees with its own tables produces "Illegal mix of
# collations" on the first join against a table created afterwards.

zcat "$DUMP" | run_sql "$TARGET"

TABLES=$(run_sql <<SQL | tail -1
SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '${TARGET}';
SQL
)
echo "--- restored: ${TARGET} now holds ${TABLES} tables ---"
