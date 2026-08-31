#!/bin/bash
# Install the backup timers on a host, idempotently, after checking the one
# thing the job itself cannot check.
#
# tools/db_backup.py runs inside a container where the MariaDB data directory is
# not mounted, so all it can compare is paths. The failure this repository
# actually had is a destination on a *different path on the same disk*:
# /muma/backups and /docker/music-management/mariadb were both on
# /dev/mapper/pve-vm--107--disk--0. Only the host can see that, so the check
# lives here and refuses to install a schedule that would produce comforting,
# worthless dumps.
#
# Usage (as root, on the host that runs the stack):
#   scripts/backup/install-systemd.sh /path/to/repo/.env
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="${1:-$PROJECT_ROOT/.env}"
TARGET_DIR=/opt/muma-backup

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
[ -f "$ENV_FILE" ] || { echo "no env file at $ENV_FILE" >&2; exit 1; }

# shellcheck disable=SC1090
set -a && . "$ENV_FILE" && set +a

: "${HOST_BACKUP_PATH:?HOST_BACKUP_PATH is not set in $ENV_FILE}"
: "${HOST_DATA_PATH:?HOST_DATA_PATH is not set in $ENV_FILE}"

DATA_DIR="$HOST_DATA_PATH/mariadb"
mkdir -p "$HOST_BACKUP_PATH"

[ -d "$DATA_DIR" ] || { echo "data directory $DATA_DIR does not exist" >&2; exit 1; }

BACKUP_DEV=$(stat -c %d "$HOST_BACKUP_PATH")
DATA_DEV=$(stat -c %d "$DATA_DIR")
if [ "$BACKUP_DEV" = "$DATA_DEV" ]; then
    cat >&2 <<EOF
refusing to install.

  HOST_BACKUP_PATH  $HOST_BACKUP_PATH
  data directory    $DATA_DIR

are on the same device ($BACKUP_DEV). A dump there survives none of the things a
backup is for, and having one is worse than having none, because it looks like
cover. Point HOST_BACKUP_PATH at separate storage -- on the Proxmox hosts that
means giving the container a mount point for the backup share:

  pct set <vmid> -mp3 /mnt/pve/smb-backups,mp=/mnt/backups && pct reboot <vmid>
EOF
    exit 1
fi

echo "--- destination ok: $HOST_BACKUP_PATH is on a different device than $DATA_DIR ---"

install -d -m 0755 "$TARGET_DIR"
install -m 0640 "$ENV_FILE" "$TARGET_DIR/.env"
install -m 0644 "$PROJECT_ROOT/docker/docker-compose.tools.yml" "$TARGET_DIR/"

for unit in muma-db-backup muma-db-backup-stale muma-db-restore-check; do
    install -m 0644 "$SCRIPT_DIR/systemd/$unit.service" /etc/systemd/system/
    install -m 0644 "$SCRIPT_DIR/systemd/$unit.timer" /etc/systemd/system/
done

systemctl daemon-reload
for unit in muma-db-backup muma-db-backup-stale muma-db-restore-check; do
    systemctl enable --now "$unit.timer"
done

echo
systemctl list-timers --no-pager 'muma-db-*' || true
echo
echo "--- installed. First backup runs at the next timer window; force one with: ---"
echo "    systemctl start muma-db-backup.service"
