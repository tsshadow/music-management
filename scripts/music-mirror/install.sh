#!/usr/bin/env bash
# Install one side of the music mirror (issue #25, docs/designs/music-mirror/technical.md).
#
# A person runs this, as root, on the NAS it names. It prints every change first and
# applies them only after the person types "yes". Running it again changes nothing that is
# already in place.
#
#   mirror NAS:   scripts/music-mirror/install.sh mirror  --source muma-mirror@<library NAS> \
#                     --dataset <pool>/<dataset> [--expected-dirs EPs,Soundcloud,Youtube,artists]
#   library NAS:  scripts/music-mirror/install.sh library --library <library dataset mount> \
#                     --status-dir <HOST_BACKUP_PATH>/music-mirror --from <mirror NAS address> \
#                     --read-key <muma-mirror-read.pub> --status-key <muma-mirror-status.pub>
#
# Order: mirror first (it makes the two keys), copy the two .pub files it prints to the
# library NAS, then library. The first copy is a separate, watched step:
#   sudo -u muma-mirror /opt/muma-mirror/bin/music_mirror.py --initial
set -euo pipefail

ACCOUNT=muma-mirror
BASE=/opt/muma-mirror
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

usage() {
    sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
}

die() {
    echo "install.sh: $*" >&2
    exit 1
}

# --- the plan: every change is one step, printed in the dry run and run after "yes" ---

APPLY=0
STEPS=0

# step <description> <command> [args...]: print it, or run it.
step() {
    local description=$1
    shift
    STEPS=$((STEPS + 1))
    if [ "$APPLY" = 1 ]; then
        echo "--- $description"
        "$@"
    else
        printf '  %2d. %s\n      %s\n' "$STEPS" "$description" "$*"
    fi
}

# write_file <path> <mode> <owner:group> <content>: create or replace one file.
write_file() {
    local path=$1 mode=$2 owner=$3 content=$4
    if [ -f "$path" ] && [ "$(cat "$path")" = "$content" ]; then
        return 0
    fi
    if [ "$APPLY" = 1 ]; then
        echo "--- write $path"
        install -m "$mode" -o "${owner%%:*}" -g "${owner##*:}" /dev/null "$path"
        printf '%s\n' "$content" >"$path"
    else
        STEPS=$((STEPS + 1))
        printf '  %2d. write %s (mode %s, %s):\n' "$STEPS" "$path" "$mode" "$owner"
        printf '%s\n' "$content" | sed 's/^/        | /'
    fi
}

need() {
    command -v "$1" >/dev/null 2>&1 || die "$1 is not installed here; $2"
}

# --- the mirror NAS ---

plan_mirror() {
    [ -n "${SOURCE:-}" ] || die "--source is required"
    [ -n "${DATASET:-}" ] || die "--dataset is required"
    need rsync "the job copies with it"
    need python3 "the job is a Python script"
    need zfs "the mirror must be a ZFS dataset, for its snapshots"
    need ssh-keygen "the job's two keys are made with it"
    zfs list -H -o name "$DATASET" >/dev/null 2>&1 || die "no ZFS dataset $DATASET"
    local mountpoint
    mountpoint=$(zfs get -H -o value mountpoint "$DATASET")
    [ -d "$mountpoint" ] || die "$DATASET is not mounted (mountpoint $mountpoint)"
    DEST=$mountpoint

    if ! id "$ACCOUNT" >/dev/null 2>&1; then
        step "create the account $ACCOUNT, no password, no login shell" \
            useradd --system --create-home --home-dir "$BASE/home" --shell /usr/sbin/nologin "$ACCOUNT"
    fi
    step "make $BASE/bin (root) and $BASE/keys, $BASE/state ($ACCOUNT)" \
        install -d -m 0755 -o root -g root "$BASE" "$BASE/bin"
    step "make the key and state directories" \
        install -d -m 0700 -o "$ACCOUNT" -g "$ACCOUNT" "$BASE/keys" "$BASE/state"
    step "install the job as root-owned, so the account cannot change what it runs" \
        install -m 0755 -o root -g root "$REPO_ROOT/tools/music_mirror.py" "$BASE/bin/music_mirror.py"
    for key in read status; do
        if [ ! -f "$BASE/keys/muma-mirror-$key" ]; then
            step "make the $key key (ed25519, no passphrase: cron runs it)" \
                runuser -u "$ACCOUNT" -- ssh-keygen -q -t ed25519 -N '' -C "muma-mirror-$key" -f "$BASE/keys/muma-mirror-$key"
        fi
    done
    step "let $ACCOUNT write the mirror tree" chown "$ACCOUNT:$ACCOUNT" "$DEST"
    step "let $ACCOUNT take and remove snapshots of $DATASET, nothing else in the pool" \
        zfs allow -u "$ACCOUNT" snapshot,destroy,mount "$DATASET"
    step "pin the library NAS's host key for $ACCOUNT (check the fingerprint it prints)" \
        pin_host_key "${SOURCE#*@}"

    local env
    env="# Read by $BASE/bin/music_mirror.py. Design: docs/designs/music-mirror/technical.md.
MIRROR_SOURCE=$SOURCE
MIRROR_READ_KEY=$BASE/keys/muma-mirror-read
MIRROR_STATUS_KEY=$BASE/keys/muma-mirror-status
MIRROR_DEST=$DEST
MIRROR_DATASET=$DATASET
MIRROR_STATE_DIR=$BASE/state
MIRROR_EXPECTED_DIRS=${EXPECTED_DIRS:-}
MIRROR_MAX_CHANGED_PERCENT=5
MIRROR_MAX_CHANGED_GB=200
MIRROR_POOL_WARN_PERCENT=80
MIRROR_SAMPLE_SIZE=200
MIRROR_FULL_CHECKSUM_MONTHLY=1
MIRROR_RSYNC=$(command -v rsync)
MIRROR_SSH=$(command -v ssh)
MIRROR_ZFS=$(command -v zfs)
# A push on failure goes straight to ntfy: the NAS has no database. Fill these by hand.
MIRROR_NTFY_URL=
MIRROR_NTFY_TOPIC=
MIRROR_NTFY_TOKEN="
    if [ -f "$BASE/env" ]; then
        echo "  (keeping the existing $BASE/env; compare it with the plan below by hand)"
    else
        write_file "$BASE/env" 0640 "root:$ACCOUNT" "$env"
    fi
    write_file /etc/cron.d/muma-mirror 0644 root:root "# The music mirror, nightly (issue #25).
30 1 * * * $ACCOUNT $BASE/bin/music_mirror.py >>$BASE/state/run.log 2>&1"
}

pin_host_key() {
    local host=$1 home known
    home=$(getent passwd "$ACCOUNT" | cut -d: -f6)
    known="$home/.ssh/known_hosts"
    install -d -m 0700 -o "$ACCOUNT" -g "$ACCOUNT" "$home/.ssh"
    ssh-keyscan -t ed25519 "$host" 2>/dev/null >"$known.new"
    ssh-keygen -lf "$known.new"
    mv "$known.new" "$known"
    chown "$ACCOUNT:$ACCOUNT" "$known"
}

after_mirror() {
    cat <<EOF

Next, on the library NAS, with the two public keys from this NAS:
  $BASE/keys/muma-mirror-read.pub
  $BASE/keys/muma-mirror-status.pub
run: scripts/music-mirror/install.sh library ... --read-key <read.pub> --status-key <status.pub>
Then fill MIRROR_NTFY_* in $BASE/env and start the first copy, watched:
  sudo -u $ACCOUNT $BASE/bin/music_mirror.py --initial
EOF
}

# --- the library NAS ---

plan_library() {
    [ -n "${LIBRARY:-}" ] || die "--library is required"
    [ -n "${STATUS_DIR:-}" ] || die "--status-dir is required"
    [ -n "${FROM:-}" ] || die "--from (the mirror NAS address) is required"
    [ -f "${READ_KEY:-}" ] || die "--read-key must name the muma-mirror-read.pub file"
    [ -f "${STATUS_KEY:-}" ] || die "--status-key must name the muma-mirror-status.pub file"
    [ -d "$LIBRARY" ] || die "no library at $LIBRARY"
    local rrsync
    rrsync=$(command -v rrsync || true)
    [ -n "$rrsync" ] || die "rrsync is not installed (rsync 3.2+ ships it); the keys depend on it"
    case "$FROM" in *[!A-Za-z0-9.:-]*) die "--from must be one address or host name" ;; esac

    if ! id "$ACCOUNT" >/dev/null 2>&1; then
        step "create the account $ACCOUNT, no password" \
            useradd --system --create-home --shell /bin/sh "$ACCOUNT"
    fi
    local home
    home=$(getent passwd "$ACCOUNT" | cut -d: -f6)
    home=${home:-/home/$ACCOUNT}
    step "make the status directory, writable by $ACCOUNT only" \
        install -d -m 0755 -o "$ACCOUNT" -g "$ACCOUNT" "$STATUS_DIR"
    step "make $home/.ssh" install -d -m 0700 -o "$ACCOUNT" -g "$ACCOUNT" "$home/.ssh"
    local options='restrict,from="'"$FROM"'"'
    write_file "$home/.ssh/authorized_keys" 0600 "$ACCOUNT:$ACCOUNT" "# The music mirror (issue #25). Each key runs one fixed command.
$options,command=\"$rrsync -ro $LIBRARY\" $(cut -d' ' -f1,2 "$READ_KEY") muma-mirror-read
$options,command=\"$rrsync -wo $STATUS_DIR\" $(cut -d' ' -f1,2 "$STATUS_KEY") muma-mirror-status"
}

after_library() {
    cat <<EOF

The library can be read by the mirror NAS ($FROM) as $ACCOUNT, and only read.
Read access to the library for $ACCOUNT is the SMB share's or the dataset's ACL: check
  sudo -u $ACCOUNT ls $LIBRARY
If the status directory is not where production's HOST_BACKUP_PATH points, production
cannot see the status. On production, set MIRROR_STATUS_PATH=/backups/music-mirror in the
.env, deploy, and run scripts/backup/install-systemd.sh again for the daily check.
EOF
}

# --- main ---

[ $# -ge 1 ] || usage
ROLE=$1
shift
while [ $# -gt 0 ]; do
    case "$1" in
        --source) SOURCE=$2 ;;
        --dataset) DATASET=$2 ;;
        --expected-dirs) EXPECTED_DIRS=$2 ;;
        --library) LIBRARY=$2 ;;
        --status-dir) STATUS_DIR=$2 ;;
        --from) FROM=$2 ;;
        --read-key) READ_KEY=$2 ;;
        --status-key) STATUS_KEY=$2 ;;
        -h | --help) usage ;;
        *) die "unknown option $1" ;;
    esac
    shift 2
done

case "$ROLE" in
    mirror | library) ;;
    *) usage ;;
esac
[ "$(id -u)" -eq 0 ] || die "run as root"

echo "Changes for the $ROLE side of the music mirror:"
"plan_$ROLE"
if [ "$STEPS" = 0 ]; then
    echo "  nothing: everything is in place."
    exit 0
fi
echo
read -r -p "Type yes to apply these $STEPS changes: " answer
[ "$answer" = yes ] || die "nothing changed"

APPLY=1
STEPS=0
"plan_$ROLE"
"after_$ROLE"
