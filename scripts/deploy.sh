#!/bin/bash
# Comprehensive Docker Stack Deployment Script
# Handles: Webhooks, Remote SSH updates, and Database Migrations.
#
# Remote deploy order: prepare (disk check, db up + ready) -> verified pre-deploy
# dump -> db recreate (DEPLOY_DB=1 only) -> migrations -> DEPLOY_PRE_UP_HOOK ->
# pull + up of what changed. See the comment above step 2 below and
# docs/self-hosting.md. Unused images are pruned afterwards by
# scripts/ci/prune-prod-images.sh, once post-deploy verification has passed.
#
# Knobs (environment; all optional):
#   IMAGE_TAG=<tag>       deploy that tag of every image this repo builds
#                         instead of :latest -- the rollback lever
#   DEPLOY_DB=1           also (re)create the `db` container when its
#                         definition changed -- after the pre-deploy dump;
#                         otherwise it is only started when missing, never
#                         recreated
#   DEPLOY_MIN_FREE_GB=8  refuse to deploy when the host has less free space
#                         than this on DEPLOY_DISK_CHECK_PATH (default /): a
#                         pull into a full disk half-deploys (bug report 094)
#   DB_UPGRADE_WAIT_SECONDS=600  how long a recreated `db` may take to answer
#                         over TCP, mariadb-upgrade included
#   DEPLOY_ONESHOTS=1     also start the one-shot tool containers
#                         (soundcloud-fetcher, genre-processor)
#   PREDEPLOY_BACKUP=0    skip the pre-deploy dump (loudly); for emergencies
#   DEPLOY_PRE_UP_HOOK=<cmd>  run locally after the migrations, before `up`
#   MIGRATION_LOCK_WAIT_SECONDS=120  how long one migration may wait for a lock
#                         before it errors and the deploy stops (bug report 068)
#   PREDEPLOY_DUMP_STALL_SECONDS=300  how long the fallback pre-deploy dump may
#                         produce no output before it is stopped (bug report 068)
#   PREDEPLOY_BACKUP_RM_WAIT_SECONDS=60  how long a failed db-backup run's
#                         container may take to disappear before the fallback
#                         dump is refused rather than started (bug report 123)

set -e

# Nothing secret may appear on a command line in this script: argv is readable
# through `ps` by every account on the runner and, for the remote half, on the
# production host. Secrets travel on ssh's stdin instead. See
# docs/bug-reports/038-deploy-puts-every-prod-secret-on-the-command-line.md.

# run_ssh HOST USER PASS CMD: run CMD on HOST, passing this shell's stdin through.
# CMD itself must never contain a secret. The password, when one is used, goes
# to sshpass through the SSHPASS environment variable rather than `-p`.
run_ssh() {
    local host="$1"
    local user="$2"
    local pass="$3"
    local cmd="$4"

    if [ -z "$host" ] || [ -z "$user" ]; then
        return 1
    fi

    # Pinned host key for production, accept-new elsewhere (scripts/lib/ssh_host_keys.sh).
    local -a key_opts
    ssh_host_key_opts_into key_opts "$host" || return 1

    if [ -z "$pass" ]; then
        ssh "${key_opts[@]}" "${user}@${host}" "${cmd}"
    elif command -v sshpass >/dev/null 2>&1; then
        SSHPASS="${pass}" sshpass -e ssh "${key_opts[@]}" "${user}@${host}" "${cmd}"
    else
        echo "Error: sshpass not found. Install it or unset password variable."
        exit 1
    fi
}

# Ensure we are in the project root if possible, or handle relative paths
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=scripts/lib/dotenv.sh
. "$SCRIPT_DIR/lib/dotenv.sh"
# shellcheck source=scripts/lib/ssh_host_keys.sh
. "$SCRIPT_DIR/lib/ssh_host_keys.sh"
# shellcheck source=scripts/lib/compose_profiles.sh
. "$SCRIPT_DIR/lib/compose_profiles.sh"

# The env file is both the configuration of this script and the file shipped
# to the host for the stack. It may be absolute: ci-deploy.sh materialises it in
# a private temp directory, outside the checkout and therefore outside every
# docker build context.
LOCAL_ENV_FILE="${LOCAL_ENV_FILE:-.env}"
case "$LOCAL_ENV_FILE" in
    /*) ENV_PATH="$LOCAL_ENV_FILE" ;;
    *) ENV_PATH="$PROJECT_ROOT/$LOCAL_ENV_FILE" ;;
esac

# Load .env variables
if [ -f "$ENV_PATH" ]; then
    echo "--- Loading environment from $ENV_PATH ---"
    dotenv_load "$ENV_PATH"
fi

# Configuration
STACK_NAME="${DEPLOY_TARGET_NAME:-muma}"
STACK_NAME=$(echo "$STACK_NAME" | tr '[:upper:]' '[:lower:]')
SERVICE_NAME="${SERVICE_NAME}"
IMAGE_NAME="${IMAGE_NAME}"

# Parse positional arguments for service name
for arg in "$@"; do
    case $arg in
        --debug|--remote|--semi-remote|--skip-lint|--skip-test) ;;
        *) 
            if [ -z "$SERVICE_NAME" ]; then
                SERVICE_NAME="$arg"
                # Map shorthand names to service names in docker-compose.yml
                if [ "$SERVICE_NAME" == "manager" ]; then SERVICE_NAME="music-manager"; fi
            fi
            ;;
    esac
done
TAG="${TAG:-latest}"
SEARCH_STRING="${SEARCH_STRING:-}"
LOCAL_COMPOSE_FILE="${LOCAL_COMPOSE_FILE:-docker/docker-compose.yml}"

# Deploy-order knobs, see the header.
DEPLOY_DB="${DEPLOY_DB:-0}"
DEPLOY_ONESHOTS="${DEPLOY_ONESHOTS:-0}"
PREDEPLOY_BACKUP="${PREDEPLOY_BACKUP:-1}"
# One-shot jobs that live in docker/docker-compose.yml with `restart: "no"`.
# Starting them on every deploy re-ran a full SoundCloud fetch each release.
ONESHOT_SERVICES="soundcloud-fetcher genre-processor"
# Where scripts/backup/install-systemd.sh put the backup compose file and env.
BACKUP_COMPOSE_DIR="${BACKUP_COMPOSE_DIR:-/opt/muma-backup}"
# Same floor as tools/db_backup.py (MIN_SIZE_BYTES): above "mariadb-dump printed
# an error and quit", far below the ~780 MB a real dump is.
PREDEPLOY_DUMP_MIN_BYTES="${PREDEPLOY_DUMP_MIN_BYTES:-1048576}"
PREDEPLOY_DUMPS_KEPT="${PREDEPLOY_DUMPS_KEPT:-3}"
DB_WAIT_SECONDS="${DB_WAIT_SECONDS:-180}"
# A migration waiting longer than this for a lock errors instead of hanging the
# job until its timeout (docs/bug-reports/068-deploy-hangs-on-no-op-alter-metadata-lock.md).
MIGRATION_LOCK_WAIT_SECONDS="${MIGRATION_LOCK_WAIT_SECONDS:-120}"
# The fallback dump is stopped once its file has not grown for this long; the
# db-backup service has the same watchdog in tools/db_backup.py (BACKUP_STALL_SECONDS).
PREDEPLOY_DUMP_STALL_SECONDS="${PREDEPLOY_DUMP_STALL_SECONDS:-300}"
# The fallback dump starts only once a failed db-backup run's container is gone;
# this is how long `docker rm -f` gets to make it so (bug report 123).
PREDEPLOY_BACKUP_RM_WAIT_SECONDS="${PREDEPLOY_BACKUP_RM_WAIT_SECONDS:-60}"
# The disk pre-check (bug report 094). 8 GB is roughly one release's worth of
# fresh image layers plus a pre-deploy dump with room to spare; production ran
# into 95% full with 5.5 GB left after images piled up for months.
DEPLOY_MIN_FREE_GB="${DEPLOY_MIN_FREE_GB:-8}"
DEPLOY_DISK_CHECK_PATH="${DEPLOY_DISK_CHECK_PATH:-/}"
# A recreated db on a new major runs mariadb-upgrade (MARIADB_AUTO_UPGRADE) on a
# temporary server before the real one listens; give that its own, longer wait.
DB_UPGRADE_WAIT_SECONDS="${DB_UPGRADE_WAIT_SECONDS:-600}"
case "$PREDEPLOY_DUMP_MIN_BYTES$PREDEPLOY_DUMPS_KEPT$DB_WAIT_SECONDS$MIGRATION_LOCK_WAIT_SECONDS$PREDEPLOY_DUMP_STALL_SECONDS$PREDEPLOY_BACKUP_RM_WAIT_SECONDS$DEPLOY_MIN_FREE_GB$DB_UPGRADE_WAIT_SECONDS" in
    *[!0-9]*) echo "Error: PREDEPLOY_DUMP_MIN_BYTES, PREDEPLOY_DUMPS_KEPT, DB_WAIT_SECONDS, MIGRATION_LOCK_WAIT_SECONDS, PREDEPLOY_DUMP_STALL_SECONDS, PREDEPLOY_BACKUP_RM_WAIT_SECONDS, DEPLOY_MIN_FREE_GB and DB_UPGRADE_WAIT_SECONDS must be numbers."; exit 1 ;;
esac
# Interpolated into the remote shell, so held to plain path characters.
if ! printf '%s' "$DEPLOY_DISK_CHECK_PATH" | grep -Eq '^/[A-Za-z0-9_./-]*$'; then
    echo "Error: DEPLOY_DISK_CHECK_PATH must be an absolute path of plain characters."
    exit 1
fi

# 1. Trigger Portainer Webhook if configured
if [ -n "${PORTAINER_WEBHOOK_URL}" ]; then
    echo "--- Triggering Portainer Webhook for: $STACK_NAME ---"
    if command -v curl >/dev/null 2>&1; then
        STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${PORTAINER_WEBHOOK_URL}")
        if [ "$STATUS_CODE" -ge 200 ] && [ "$STATUS_CODE" -lt 300 ]; then
            echo "--- Webhook triggered successfully (Status: $STATUS_CODE) ---"
        elif [ "$STATUS_CODE" -eq 404 ]; then
            echo "Error: Portainer Webhook returned 404 Not Found."
            echo "Note: Stack Webhooks are a Business Edition feature."
            exit 1
        else
            echo "Error: Portainer Webhook failed with status code $STATUS_CODE"
            exit 1
        fi
    else
        echo "Error: curl not found. Cannot trigger Portainer Webhook."
        exit 1
    fi
fi

# 2. Remote Deployment via SSH if configured
#
# The order below is the point of this block; see
# docs/bug-reports/050-deploy-starts-new-code-before-migrations.md.
#
#   a. prepare   refuse to start on a nearly full disk, ship the compose file,
#                make sure `db` runs (never recreating it here) and wait until
#                it answers
#   b. backup    a verified pre-deploy dump; no dump, no deploy
#   c. db        DEPLOY_DB=1 only: pull and, if its definition changed,
#                recreate `db`, wait for the real server (not the entrypoint's
#                temporary upgrade server) and check mariadb-upgrade ran.
#                After (b), so the newest backup predates the new MariaDB
#   d. migrate   every migrate_*.sql, while the *old* containers still run --
#                migrations are expand-only (tests/ci/test_migration_ordering.py),
#                so the old code keeps working on the new schema
#   e. hook      DEPLOY_PRE_UP_HOOK, if set; CI promotes the release's images
#                to :latest here (scripts/ci/promote-release-images.sh), so
#                Watchtower cannot start new code before (d) has finished
#   f. up        pull and recreate what changed -- never `db` (that was (c)),
#                and not the one-shot tool containers unless asked for
#
# Before this order the stack was recreated first (every container, `db`
# included, with --force-recreate) and migrated afterwards, with no backup.
# Until bug report 094, DEPLOY_DB=1 recreated `db` in (a), before the dump.
if [ -n "${REMOTE_HOST}" ] && [ -n "${REMOTE_USER}" ]; then
    echo "--- Starting remote deployment for stack: $STACK_NAME on $REMOTE_HOST ---"

    # The remote compose file is found by the image name it holds, <registry user>/muma.
    # There is no default registry user: guessing one would match the wrong stack (or none).
    if [ -z "$SEARCH_STRING" ]; then
        if [ -z "${DOCKER_USER:-}" ]; then
            echo "Error: DOCKER_USER is not set (and SEARCH_STRING is not given). Set DOCKER_USER in the .env of this deploy." >&2
            exit 1
        fi
        SEARCH_STRING="${DOCKER_USER}/muma"
    fi

    # Discovery command to be run on remote hosts
    DISCOVERY_CMD="
        ACTUAL_COMPOSE_FILE=\"\"
        if [ -n \"$STACK_NAME\" ]; then
            CONTAINER_ID=\$(docker ps -q --filter \"label=com.docker.compose.project=$STACK_NAME\" | head -n 1)
            if [ -n \"\$CONTAINER_ID\" ]; then
                ACTUAL_COMPOSE_FILE=\$(docker inspect \"\$CONTAINER_ID\" --format '{{ index .Config.Labels \"com.docker.compose.project.config_files\" }}' 2>/dev/null | cut -d, -f1)
            fi
        fi
        if ([ -z \"\$ACTUAL_COMPOSE_FILE\" ] || [ ! -f \"\$ACTUAL_COMPOSE_FILE\" ]) && [ -n \"$SERVICE_NAME\" ]; then
            ACTUAL_COMPOSE_FILE=\$(docker inspect \"$SERVICE_NAME\" --format '{{ index .Config.Labels \"com.docker.compose.project.config_files\" }}' 2>/dev/null | cut -d, -f1)
        fi
        if ([ -z \"\$ACTUAL_COMPOSE_FILE\" ] || [ ! -f \"\$ACTUAL_COMPOSE_FILE\" ]) && [ -n \"$REMOTE_STACK_PATH\" ]; then
            if [ -f \"\$REMOTE_STACK_PATH\" ]; then ACTUAL_COMPOSE_FILE=\"\$REMOTE_STACK_PATH\"; fi
        fi
        if [ -z \"\$ACTUAL_COMPOSE_FILE\" ] || [ ! -f \"\$ACTUAL_COMPOSE_FILE\" ]; then
            for SEARCH_DIR in /data/compose /var/lib/docker/volumes/*/ _data/compose /var/lib/docker/volumes/portainer_portainer_data/_data/compose; do
                if [ -d \"\$SEARCH_DIR\" ]; then
                    MATCH=\$(grep -rl \"$SEARCH_STRING\" \"\$SEARCH_DIR\" 2>/dev/null | grep \"docker-compose.yml\" | head -n 1)
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

    # Use local compose file if provided (Source of truth)
    if [ -f "$PROJECT_ROOT/$LOCAL_COMPOSE_FILE" ]; then
        echo "Using local configuration file: $LOCAL_COMPOSE_FILE"
        COMPOSE_CONTENT=$(expand -t 4 "$PROJECT_ROOT/$LOCAL_COMPOSE_FILE")
    else
        echo "Local compose file not found, attempting discovery on remote..."
        RESULT=$(run_ssh "$REMOTE_HOST" "$REMOTE_USER" "$REMOTE_PASS" "REMOTE_STACK_PATH='$REMOTE_STACK_PATH' $DISCOVERY_CMD" 2>/dev/null || true)
        if echo "$RESULT" | grep -q "^FOUND_FILE:"; then
            COMPOSE_CONTENT=$(echo "$RESULT" | sed -n '/^FOUND_FILE:/!p' | expand -t 4)
            echo "Found existing configuration on $REMOTE_HOST"
        fi
    fi

    if [ -z "$COMPOSE_CONTENT" ]; then
        echo "Error: No docker-compose configuration found."
        exit 1
    fi

    # Source workers sit behind compose profiles: without COMPOSE_PROFILES in the
    # env file a deploy starts none of them, and compose v2 removes the running
    # ones as orphans. Refuse before anything changes. A declared profile that the
    # value leaves out is skipped in the update loop below on v1 and v2 alike
    # (v1 would otherwise start it, because it is named on the command line); a
    # container of it that is already running is left running.
    # docs/self-hosting.md#source-workers-are-compose-profiles
    PROFILE_SKIPPED_SERVICES=""
    DECLARED_PROFILES=$(compose_service_profiles "$COMPOSE_CONTENT" | awk '{print $2}' | sort -u | tr '\n' ' ')
    if [ -n "$DECLARED_PROFILES" ] && [ -f "$ENV_PATH" ]; then
        if ! ENABLED_PROFILES=$(compose_profiles_value "$(cat "$ENV_PATH")"); then
            echo "Error: the compose file declares the profiles ${DECLARED_PROFILES}but the env file has no non-empty COMPOSE_PROFILES line, so no source worker would be started. Add e.g. COMPOSE_PROFILES=soundcloud,youtube,telegram,importer (docs/self-hosting.md#source-workers-are-compose-profiles)."
            exit 1
        fi
        PROFILE_SKIPPED_SERVICES=$(compose_disabled_services "$COMPOSE_CONTENT" "$ENABLED_PROFILES")
        for P in $DECLARED_PROFILES; do
            case ",$ENABLED_PROFILES," in
                *",$P,"*) ;;
                *) echo "Note: profile '$P' is not in COMPOSE_PROFILES; its services are not updated or started here. A container of it that already runs is left running; stop it by hand." ;;
            esac
        done
    fi

    # The compose file is no secret (it is the tracked file), so it may ride on
    # the command line; the env file may not.
    B64_DATA=$(echo "$COMPOSE_CONTENT" | base64 -w 0)
    SEND_ENV=0
    if [ -f "$ENV_PATH" ]; then
        SEND_ENV=1
    fi

    # Root when the env carries its password, the application user otherwise.
    # Used by the migrations and by the fallback dump.
    MIGRATION_USER="$DB_USER"
    MIGRATION_PASS="$DB_PASS"
    if [ -n "$MYSQL_ROOT_PASSWORD" ]; then
        MIGRATION_USER="root"
        MIGRATION_PASS="$MYSQL_ROOT_PASSWORD"
    fi

    # IMAGE_TAG is the one-variable rollback (docs/self-hosting.md#roll-back):
    # docker/docker-compose.yml names every image this repository builds as
    # ${IMAGE_TAG:-latest}. Not a secret, so it may travel on the command line,
    # but it is checked to be a tag and nothing else before it is interpolated
    # into a remote shell.
    IMAGE_TAG_EXPORT=""
    if [ -n "${IMAGE_TAG:-}" ]; then
        if ! printf '%s' "$IMAGE_TAG" | grep -Eq '^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$'; then
            echo "Error: IMAGE_TAG '$IMAGE_TAG' is not a valid image tag."
            exit 1
        fi
        IMAGE_TAG_EXPORT="export IMAGE_TAG='$IMAGE_TAG'"
        echo "--- Deploying image tag: $IMAGE_TAG ---"
    fi

    # Services the final `up` leaves alone (see the header of this block). `db`
    # always: step (c) is the only place it is ever recreated, after the dump.
    SKIP_SERVICES="db"
    if [ "$DEPLOY_ONESHOTS" != "1" ]; then
        SKIP_SERVICES="$SKIP_SERVICES $ONESHOT_SERVICES"
    fi

    # Shared prelude of the remote steps that run compose (prepare, db, up).
    #
    # Everything lands in a root-only directory under the remote user's home,
    # not in world-writable /tmp: a file another account can pre-create or
    # swap there is a file root would hand to compose. The compose file stays
    # (it holds no secrets, and the container labels point at it); the env file
    # is written into a per-run directory that the EXIT trap removes as soon as
    # compose is done with it. compose only reads --env-file while it parses the
    # project, so nothing needs it afterwards. A run killed before its trap
    # fired is cleaned up by the next one (the rm of run.*).
    #
    # The env content arrives on stdin, never on the command line -- once per
    # step, because each step's trap deletes it again.
    REMOTE_PRELUDE="
        set -e
        umask 077
        DEPLOY_ROOT=\"\${HOME:?}/.muma-deploy\"
        DEPLOY_DIR=\"\$DEPLOY_ROOT/$STACK_NAME\"
        mkdir -p \"\$DEPLOY_DIR\"
        chmod 700 \"\$DEPLOY_ROOT\" \"\$DEPLOY_DIR\"
        rm -rf \"\$DEPLOY_DIR\"/run.*
        RUN_DIR=\$(mktemp -d \"\$DEPLOY_DIR/run.XXXXXX\")
        trap 'rm -rf \"\$RUN_DIR\"' EXIT
        trap 'exit 1' HUP INT TERM

        FINAL_COMPOSE_FILE=\"\$DEPLOY_DIR/docker-compose.yml\"
        echo '$B64_DATA' | base64 -d > \"\$FINAL_COMPOSE_FILE\"

        ENV_ARG=\"\"
        if [ \"$SEND_ENV\" = 1 ]; then
            FINAL_ENV_FILE=\"\$RUN_DIR/.env\"
            cat > \"\$FINAL_ENV_FILE\"
            ENV_ARG=\"--env-file \$FINAL_ENV_FILE\"
        fi

        # No lookup in /tmp: this runs as root, and an executable any local
        # account could drop into /tmp would be run as root on the next deploy.
        if docker compose version >/dev/null 2>&1; then
            DOCKER_CMD=\"docker compose \$ENV_ARG -f \$FINAL_COMPOSE_FILE -p $STACK_NAME\"
        elif command -v docker-compose >/dev/null 2>&1; then
            DOCKER_CMD=\"docker-compose \$ENV_ARG -f \$FINAL_COMPOSE_FILE -p $STACK_NAME\"
        else
            echo \"Error: No docker-compose command found on remote.\"
            exit 1
        fi
        $IMAGE_TAG_EXPORT
    "

    # remote_compose_step CMD: run the prelude plus CMD on the host, with the
    # env file (if any) on stdin.
    remote_compose_step() {
        if [ "$SEND_ENV" = 1 ]; then
            run_ssh "$REMOTE_HOST" "$REMOTE_USER" "$REMOTE_PASS" "$REMOTE_PRELUDE
$1" < "$ENV_PATH"
        else
            run_ssh "$REMOTE_HOST" "$REMOTE_USER" "$REMOTE_PASS" "$REMOTE_PRELUDE
$1" < /dev/null
        fi
    }

    # wait_for_db_cmd SECONDS WHAT: the remote snippet that waits until `db`
    # answers, and fails with WHAT in the message when it does not in time.
    #
    # Readiness is asked of the server itself: `mariadb-admin ping` exits 0 as
    # soon as mysqld answers, even with "access denied", so it needs no
    # credential. It asks over TCP, not the socket: the image's entrypoint runs
    # mariadb-upgrade (MARIADB_AUTO_UPGRADE) on a temporary server started with
    # --skip-networking on the very same socket, which a socket ping would take
    # for the real one -- and the migrations would then start against a server
    # the entrypoint is about to shut down. The temporary server never listens on
    # TCP, the real one does. (healthcheck.sh --connect makes the same
    # distinction; this spelling works on every image version.)
    wait_for_db_cmd() {
        printf '%s' "
            waited=0
            until docker exec music-management-db-1 mariadb-admin --protocol=tcp -h 127.0.0.1 ping --silent >/dev/null 2>&1; do
                if [ \"\$waited\" -ge $1 ]; then
                    echo 'Error: the database did not answer within $1 s; $2'
                    exit 1
                fi
                sleep 2
                waited=\$((waited + 2))
            done
            echo \"Database is answering (after \${waited}s).\"
        "
    }

    # a. prepare -------------------------------------------------------------
    #
    # The disk pre-check comes first (bug report 094): images piled up until
    # the root disk was 95% full, and a pull into a full disk fails halfway
    # through `up`, with some containers on the new release and some on the old.
    # Refusing here, before anything is dumped, pulled or migrated, changes
    # nothing on the host. DEPLOY_MIN_FREE_GB=0 switches it off.
    #
    # `db` is started when it is missing but never recreated here, not even
    # with DEPLOY_DB=1: --no-recreate leaves a running database alone even when
    # its definition changed (a new logging block, say). Recreating it is step
    # (c), after the pre-deploy dump.
    echo "--- [1/6] Preparing $STACK_NAME: disk space, compose file, database ---"
    remote_compose_step "
        MIN_KB=\$(( $DEPLOY_MIN_FREE_GB * 1024 * 1024 ))
        if [ \"\$MIN_KB\" -gt 0 ]; then
            AVAIL_KB=\$(df -Pk '$DEPLOY_DISK_CHECK_PATH' | awk 'NR == 2 { print \$4 }')
            case \"\$AVAIL_KB\" in
                ''|*[!0-9]*)
                    echo 'Error: could not read the free space on $DEPLOY_DISK_CHECK_PATH; refusing to deploy (DEPLOY_MIN_FREE_GB=0 skips this check).'
                    exit 1 ;;
            esac
            AVAIL_GB=\$(awk -v kb=\"\$AVAIL_KB\" 'BEGIN { printf \"%.1f\", kb / 1048576 }')
            if [ \"\$AVAIL_KB\" -lt \"\$MIN_KB\" ]; then
                echo \"Error: only \${AVAIL_GB} GB free on $DEPLOY_DISK_CHECK_PATH, below the $DEPLOY_MIN_FREE_GB GB this deploy needs; nothing was pulled, dumped or migrated. A pull into a full disk half-deploys. Free space first -- old images are the usual culprit: 'docker system df', then scripts/ci/prune-prod-images.sh from the runner or 'docker image prune -a -f --filter until=72h' on the host (docs/self-hosting.md#deploy-by-hand).\"
                exit 1
            fi
            echo \"Disk: \${AVAIL_GB} GB free on $DEPLOY_DISK_CHECK_PATH (minimum $DEPLOY_MIN_FREE_GB GB).\"
        fi
        if \$DOCKER_CMD config --services | grep -qx db; then
            \$DOCKER_CMD up -d --no-deps --no-recreate db
            $(wait_for_db_cmd "$DB_WAIT_SECONDS" "nothing was migrated or recreated.")
        else
            echo 'No db service in this compose file; skipping the database wait.'
        fi
    "

    # b. backup --------------------------------------------------------------
    #
    # First choice is the same entry point the nightly timer uses:
    # tools/db_backup.py, through the db-backup service of the compose file that
    # scripts/backup/install-systemd.sh installed in $BACKUP_COMPOSE_DIR. It
    # dumps, verifies (size floor, gzip stream, "-- Dump completed" trailer),
    # records row counts and prunes. BACKUP_LABEL=pre-deploy names the file
    # muma_db_pre-deploy_<stamp>.sql.gz; an older tools image that predates the
    # label ignores the variable and writes an ordinary verified daily dump,
    # which serves the same purpose.
    #
    # When that is not installed or fails, the fallback is mariadb-dump through
    # `docker exec` into the same destination, held to the same three checks.
    # The password travels as on the migrations: first line of stdin, into
    # MYSQL_PWD, `docker exec -e MYSQL_PWD` without a value.
    #
    # Either way, no verified dump means no deploy: nothing has been migrated
    # or recreated yet at this point, so stopping here changes nothing.
    if [ "$PREDEPLOY_BACKUP" = "1" ]; then
        echo "--- [2/6] Pre-deploy database backup ---"
        Q_BACKUP_COMPOSE_DIR=$(printf '%q' "$BACKUP_COMPOSE_DIR")
        Q_BACKUP_DEST=$(printf '%q' "${HOST_BACKUP_PATH:-/mnt/backups/muma}")
        Q_DB_DB=$(printf '%q' "$DB_DB")
        Q_MIGRATION_USER=$(printf '%q' "$MIGRATION_USER")
        REMOTE_BACKUP_CMD="
            set -e
            IFS= read -r DUMP_PWD || true
            BACKUP_DIR=$Q_BACKUP_COMPOSE_DIR
            if [ -f \"\$BACKUP_DIR/docker-compose.backup.yml\" ] && [ -f \"\$BACKUP_DIR/.env\" ]; then
                if docker compose version >/dev/null 2>&1; then
                    BACKUP_COMPOSE=\"docker compose\"
                else
                    BACKUP_COMPOSE=\"docker-compose\"
                fi
                # A name of our own, so the container can be found and removed
                # below whatever happens to it, and the Watchtower opt-out label:
                # on 2026-09-27 Watchtower's hourly session found a new
                # muma-tools:latest while this run was dumping, stopped the run's
                # container and recreated it under the same name -- which started
                # a second tools/db_backup.py beside the fallback dump below, both
                # writing one file (bug report 123).
                RUN_NAME=\"$STACK_NAME-predeploy-backup-\$(date -u +%Y%m%d%H%M%S)-\$\$\"
                echo \"Running the db-backup service from \$BACKUP_DIR (tools/db_backup.py) as \$RUN_NAME\"
                BACKUP_RC=0
                \$BACKUP_COMPOSE --env-file \"\$BACKUP_DIR/.env\" -f \"\$BACKUP_DIR/docker-compose.backup.yml\" -p $STACK_NAME \\
                        run --rm -T --name \"\$RUN_NAME\" -l com.centurylinklabs.watchtower.enable=false \\
                        -e BACKUP_LABEL=pre-deploy db-backup < /dev/null || BACKUP_RC=\$?
                if [ \"\$BACKUP_RC\" = 0 ]; then
                    echo 'PREDEPLOY_BACKUP_OK (db-backup service)'
                    exit 0
                fi
                # One dump writer at a time. A failed run can leave its container
                # behind -- or, as on 2026-09-27, a recreated copy of it still
                # dumping -- so it is removed, and its absence confirmed, before
                # anything else touches the backup directory.
                docker rm -f \"\$RUN_NAME\" >/dev/null 2>&1 || true
                GONE_WAIT=0
                while docker inspect --type container \"\$RUN_NAME\" >/dev/null 2>&1; do
                    if [ \"\$GONE_WAIT\" -ge $PREDEPLOY_BACKUP_RM_WAIT_SECONDS ]; then
                        echo \"Error: the db-backup container \$RUN_NAME is still there $PREDEPLOY_BACKUP_RM_WAIT_SECONDS s after docker rm -f; a fallback dump beside it would be a second writer. Refusing to deploy without a backup (bug report 123).\"
                        exit 1
                    fi
                    docker rm -f \"\$RUN_NAME\" >/dev/null 2>&1 || true
                    sleep 1
                    GONE_WAIT=\$((GONE_WAIT + 1))
                done
                # Exit 3 is tools/db_backup.py's stall watchdog: the dump stopped
                # producing output, almost certainly waiting on a metadata lock. A
                # second dump would queue behind the same lock (bug report 068).
                if [ \"\$BACKUP_RC\" = 3 ]; then
                    echo 'Error: the pre-deploy dump stalled (waiting on a table lock?); refusing to deploy without a backup. Find the lock holder in SHOW PROCESSLIST as root, see docs/self-hosting.md#migrations.'
                    exit 1
                fi
                echo 'WARNING: the db-backup service failed; falling back to mariadb-dump through docker exec.'
            else
                echo \"No backup compose file in \$BACKUP_DIR; using mariadb-dump through docker exec.\"
            fi
            # Any other db-backup container still running -- the nightly timer's,
            # an earlier deploy's -- is a dump in progress; a second one beside it
            # doubles the load and, before bug report 123, could share its file.
            OTHER_BACKUPS=\$(docker ps -q --filter label=com.docker.compose.service=db-backup 2>/dev/null || true)
            if [ -n \"\$OTHER_BACKUPS\" ]; then
                echo \"Error: another db-backup container is still running (\$(echo \$OTHER_BACKUPS)); refusing to start a second dump beside it. Wait for it to finish (docker ps --filter label=com.docker.compose.service=db-backup) and deploy again.\"
                exit 1
            fi

            if [ -z \"\$DUMP_PWD\" ]; then
                echo 'Error: no database password for the fallback dump; refusing to deploy without a backup.'
                exit 1
            fi
            DEST=$Q_BACKUP_DEST
            if [ ! -d \"\$DEST\" ]; then
                echo \"Error: backup destination \$DEST does not exist (is the backup share mounted?); refusing to deploy without a backup.\"
                exit 1
            fi
            STAMP=\$(date -u +%Y%m%d_%H%M%S)
            # Names of this writer's own: _fallback keeps the finished file apart
            # from a db-backup dump taken in the same second, and the shell's PID
            # keeps the temporary one apart from every other writer's. Both still
            # match the pre-deploy rotation and tools/db_backup.py's partial sweep.
            FILE=\"\$DEST/muma_db_pre-deploy_\${STAMP}_fallback.sql.gz\"
            PART=\"\$DEST/muma_db_pre-deploy_\${STAMP}_fallback.\$\$.sql.gz.partial\"
            STATUS_FILE=\$(mktemp)
            PID_FILE=\$(mktemp)
            trap 'rm -f \"\$STATUS_FILE\" \"\$PID_FILE\" \"\$PART\"' EXIT
            # The dump's own exit status goes through a file: in a pipe into
            # gzip it would otherwise be lost, and a dump that died halfway
            # would look like a short success.
            #
            # It runs in the background under a watchdog: mariadb-dump has no
            # lock timeout of its own (no --init-command either), so one queued
            # behind a table metadata lock waits for as long as the lock is held
            # -- in bug report 068 until the job's own timeout killed it. When the
            # file has not grown for $PREDEPLOY_DUMP_STALL_SECONDS s the client is
            # stopped and the deploy refused. The dump inside the container then
            # ends by itself once the lock clears and it finds its output gone.
            {
                MYSQL_PWD=\"\$DUMP_PWD\" docker exec -i -e MYSQL_PWD music-management-db-1 mariadb-dump \\
                    -u $Q_MIGRATION_USER --single-transaction --quick --routines --triggers --events \\
                    --default-character-set=utf8mb4 $Q_DB_DB < /dev/null &
                echo \$! > \"\$PID_FILE\"
                DUMP_RC=0
                wait \$! || DUMP_RC=\$?
                echo \"\$DUMP_RC\" > \"\$STATUS_FILE\"
            } | gzip > \"\$PART\" &
            PIPE_PID=\$!
            LAST_SIZE=-1
            STILL=0
            while kill -0 \"\$PIPE_PID\" 2>/dev/null; do
                sleep 1
                SIZE=\$(stat -c %s \"\$PART\" 2>/dev/null || echo 0)
                if [ \"\$SIZE\" = \"\$LAST_SIZE\" ]; then
                    STILL=\$((STILL + 1))
                else
                    STILL=0
                    LAST_SIZE=\$SIZE
                fi
                if [ \"\$STILL\" -ge $PREDEPLOY_DUMP_STALL_SECONDS ]; then
                    echo \"Error: the pre-deploy dump wrote nothing for $PREDEPLOY_DUMP_STALL_SECONDS s (stuck at \$SIZE bytes), most likely waiting on a table metadata lock; stopped it and refusing to deploy without a backup. Find the lock holder in SHOW PROCESSLIST as root, see docs/self-hosting.md#migrations.\"
                    if [ -s \"\$PID_FILE\" ]; then
                        kill \"\$(cat \"\$PID_FILE\")\" 2>/dev/null || true
                    fi
                    wait \"\$PIPE_PID\" 2>/dev/null || true
                    exit 1
                fi
            done
            wait \"\$PIPE_PID\" || true
            if [ \"\$(cat \"\$STATUS_FILE\")\" != 0 ]; then
                echo \"Error: mariadb-dump exited \$(cat \"\$STATUS_FILE\"); refusing to deploy without a backup.\"
                exit 1
            fi
            SIZE=\$(stat -c %s \"\$PART\")
            if [ \"\$SIZE\" -lt $PREDEPLOY_DUMP_MIN_BYTES ]; then
                echo \"Error: the dump is \$SIZE bytes, below the $PREDEPLOY_DUMP_MIN_BYTES floor; refusing to deploy without a backup.\"
                exit 1
            fi
            if ! gzip -t \"\$PART\"; then
                echo 'Error: the dump does not decompress; refusing to deploy without a backup.'
                exit 1
            fi
            if ! gzip -dc \"\$PART\" | tail -c 4096 | grep -q -- '-- Dump completed'; then
                echo 'Error: the dump has no \"-- Dump completed\" trailer (truncated); refusing to deploy without a backup.'
                exit 1
            fi
            mv \"\$PART\" \"\$FILE\"
            # Keep the newest $PREDEPLOY_DUMPS_KEPT; the nightly job prunes its own
            # files by prefix and never matches these.
            ls -1t \"\$DEST\"/muma_db_pre-deploy_*.sql.gz 2>/dev/null | tail -n +$((PREDEPLOY_DUMPS_KEPT + 1)) | xargs -r rm -f
            echo \"PREDEPLOY_BACKUP_OK \$FILE (\$SIZE bytes)\"
        "
        printf '%s\n' "$MIGRATION_PASS" \
            | run_ssh "$REMOTE_HOST" "$REMOTE_USER" "$REMOTE_PASS" "$REMOTE_BACKUP_CMD"
    else
        echo "--- [2/6] WARNING: PREDEPLOY_BACKUP=0, deploying WITHOUT a pre-deploy backup ---"
    fi

    # c. db -----------------------------------------------------------------
    #
    # DEPLOY_DB=1 is the deliberate way to roll out a change to `db`'s
    # definition, or to move MariaDB itself -- and it happens here, after the
    # verified dump of (b), so that if the new server does not come up the
    # newest backup is minutes old rather than last night's (bug report 094).
    #
    # A new major or minor MariaDB needs mariadb-upgrade on the existing data
    # directory. The compose file sets MARIADB_AUTO_UPGRADE=1, the image's
    # documented way to have its entrypoint run it (after backing the system
    # tables up to system_mysql_backup_*.sql.zst in the data directory). The
    # wait asks over TCP, so it only ends once that is done and the real server
    # listens; the entrypoint's upgrade log is printed; and the version recorded
    # in mariadb_upgrade_info must then match the server's, or the deploy stops
    # before any migration touches a data directory that was not upgraded.
    if [ "$DEPLOY_DB" = "1" ]; then
        echo "--- [3/6] DEPLOY_DB=1: pulling and, if its definition changed, recreating db ---"
        # Not a failure: nothing in either stack needs the published port. But
        # the workstation's read-only MCP does, and this is the moment it goes.
        if [ -z "${DB_BIND_ADDRESS:-}" ]; then
            echo "Note: DB_BIND_ADDRESS is not set in the env file; a recreated db publishes 3306 on 127.0.0.1 only, and the read-only MCP (tools/muma_mcp) stops reaching it (docs/self-hosting.md#configure-the-stack)."
        fi
        remote_compose_step "
            if ! \$DOCKER_CMD config --services | grep -qx db; then
                echo 'No db service in this compose file; nothing to recreate.'
                exit 0
            fi
            \$DOCKER_CMD pull db
            OLD_ID=\$(docker inspect --format '{{.Id}}' music-management-db-1 2>/dev/null || echo '')
            SINCE=\$(date -u +%Y-%m-%dT%H:%M:%SZ)
            \$DOCKER_CMD up -d --no-deps db
            NEW_ID=\$(docker inspect --format '{{.Id}}' music-management-db-1 2>/dev/null || echo '')
            if ! (
                $(wait_for_db_cmd "$DB_UPGRADE_WAIT_SECONDS" "restore from the pre-deploy dump of step 2 if the data directory is damaged. Last lines of its log:")
            ); then
                docker logs --tail 50 music-management-db-1 2>&1 || true
                exit 1
            fi
            if [ -n \"\$OLD_ID\" ] && [ \"\$OLD_ID\" = \"\$NEW_ID\" ]; then
                echo 'The db definition and image are unchanged; the container was not recreated.'
            else
                echo 'db was recreated. Its entrypoint log since then (mariadb-upgrade runs here):'
                docker logs --since \"\$SINCE\" music-management-db-1 2>&1 | grep -E 'Entrypoint|mariadb-upgrade|upgrade|ERROR' || echo '  (no entrypoint lines)'
            fi
            SERVER_VERSION=\$(docker exec music-management-db-1 mariadbd --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n 1)
            UPGRADE_INFO=\$(docker exec music-management-db-1 cat /var/lib/mysql/mariadb_upgrade_info 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n 1)
            echo \"MariaDB server \${SERVER_VERSION:-unknown}, data directory upgraded for \${UPGRADE_INFO:-unknown}.\"
            if [ -z \"\$SERVER_VERSION\" ] || [ \"\${SERVER_VERSION%.*}\" != \"\${UPGRADE_INFO%.*}\" ]; then
                echo 'Error: the data directory was not upgraded to this server version (is MARIADB_AUTO_UPGRADE set on db?); nothing was migrated. Run mariadb-upgrade in the container, or roll the db image back and restore the pre-deploy dump.'
                exit 1
            fi
        "
    else
        echo "--- [3/6] db left as it is (DEPLOY_DB=1 recreates it here, after the dump) ---"
    fi

    # d. migrate -------------------------------------------------------------
    #
    # Glob is migrate_*.sql, matching the !migrate_*.sql exception in .gitignore
    # exactly: one naming rule decides both what gets committed and what gets
    # applied, so a migration can no longer be silently skipped by one of the two
    # (see docs/bug-reports/021-genre-migration-never-shipped.md). The helper
    # sorts the files byte-wise by name -- bash's glob order follows the runner's
    # locale -- so migrate_v10_* runs before migrate_v2.sql, which runs before
    # migrate_v29_*; no migration may depend on a higher-numbered one having run
    # first. Because they run before
    # the new containers start, migrations are expand-only: the release that is
    # still running has to keep working on the migrated schema.
    #
    # tools/apply_migrations.py decides what runs (docs/bug-reports/068-deploy-
    # hangs-on-no-op-alter-metadata-lock.md):
    #   - the schema_migrations ledger records each file's name and sha256 once it
    #     applied; a recorded, unchanged file is skipped, a changed or unrecorded
    #     one runs. Every file stays re-runnable -- the ledger only saves work;
    #   - each file runs with lock_wait_timeout and innodb_lock_wait_timeout set to
    #     MIGRATION_LOCK_WAIT_SECONDS, so a statement queued behind another
    #     session's lock errors instead of hanging the job, naming the file and
    #     printing the server's sessions. The deploy stops here, before `up`.
    #
    # How the SQL gets there is unchanged. stdin carries the password on its
    # first line and the SQL after it (the helper prepends the password to every
    # batch). The remote shell reads the first line into MYSQL_PWD (the mariadb
    # client's password variable) and hands the rest of stdin straight to the
    # client; `docker exec -e MYSQL_PWD` without a value copies it from the
    # environment, so the password is on no command line -- not the ssh one here,
    # not docker's or mariadb's there -- and no SQL file is left in /tmp either.
    # Same idea as the --defaults-extra-file in tools/db_backup.py. The function
    # and the variables the helper's `bash -c` needs are exported; the
    # environment, unlike argv, is not readable by other accounts.
    #
    # The migration's exit status is the remote command's status, because docker
    # exec is its last command (bug report 021). `mariadb`, not `mysql`: MariaDB
    # dropped the old client name in 12.
    echo "--- [4/6] Applying database migrations (old containers still running) ---"
    # shellcheck disable=SC2089 # the quotes are for the remote shell that runs this string
    REMOTE_MIGRATE_CMD="
        IFS= read -r MYSQL_PWD
        export MYSQL_PWD
        docker exec -i -e MYSQL_PWD music-management-db-1 mariadb -u \"$MIGRATION_USER\" \"$DB_DB\"
    "
    # run_remote_sql: run the SQL on stdin (password first) against production.
    run_remote_sql() {
        run_ssh "$REMOTE_HOST" "$REMOTE_USER" "$REMOTE_PASS" "$REMOTE_MIGRATE_CMD"
    }
    export -f run_ssh run_remote_sql
    # shellcheck disable=SC2090 # see SC2089 above: quoting is for the remote shell
    export REMOTE_HOST REMOTE_USER REMOTE_PASS REMOTE_MIGRATE_CMD
    printf '%s\n' "$MIGRATION_PASS" \
        | python3 "$PROJECT_ROOT/tools/apply_migrations.py" --password-stdin --exec run_remote_sql \
            --lock-wait-timeout "$MIGRATION_LOCK_WAIT_SECONDS" "$PROJECT_ROOT"/migrate_*.sql

    # e. hook ----------------------------------------------------------------
    if [ -n "${DEPLOY_PRE_UP_HOOK:-}" ]; then
        echo "--- [5/6] Pre-up hook: $DEPLOY_PRE_UP_HOOK ---"
        "$DEPLOY_PRE_UP_HOOK"
    else
        echo "--- [5/6] No pre-up hook ---"
    fi

    # f. up ------------------------------------------------------------------
    #
    # No --force-recreate: compose recreates exactly the containers whose image
    # or definition changed, and leaves the rest running. --no-deps because
    # `up <service>` would otherwise converge that service's dependencies too,
    # and every service here depends on `db`.
    echo "--- [6/6] Updating containers ---"
    remote_compose_step "
        SERVICES=''
        if [ -n \"$SERVICE_NAME\" ]; then
            if ! \$DOCKER_CMD config --services | grep -qx \"$SERVICE_NAME\"; then
                echo \"Error: service '$SERVICE_NAME' is not defined in the compose file.\"
                exit 1
            fi
            SERVICES=\"$SERVICE_NAME\"
        else
            for SVC in \$(\$DOCKER_CMD config --services); do
                case \" $SKIP_SERVICES $PROFILE_SKIPPED_SERVICES \" in
                    *\" \$SVC \"*) echo \"Leaving \$SVC alone (see DEPLOY_DB / DEPLOY_ONESHOTS in scripts/deploy.sh, and COMPOSE_PROFILES)\" ;;
                    *) SERVICES=\"\$SERVICES \$SVC\" ;;
                esac
            done
        fi
        if [ -z \"\$SERVICES\" ]; then
            echo 'Error: no services left to update.'
            exit 1
        fi
        echo \"Updating:\$SERVICES\"

        \$DOCKER_CMD pull \$SERVICES

        # A container whose image has since been pruned off the host cannot be
        # recreated in place: compose stops and asks \"Continue with the new image?
        # [yN]\", which has no answer over a non-interactive ssh, so the deploy dies
        # having already recreated half the stack. Drop those containers here and
        # let 'up -d' build them fresh from the image we just pulled. Only for the
        # services being updated: removing \`db\` here would leave it removed.
        for CID in \$(docker ps -aq --filter \"label=com.docker.compose.project=$STACK_NAME\"); do
            CSVC=\$(docker inspect --format '{{ index .Config.Labels \"com.docker.compose.service\" }}' \"\$CID\" 2>/dev/null || echo '')
            case \" \$SERVICES \" in *\" \$CSVC \"*) ;; *) continue ;; esac
            CIMG=\$(docker inspect --format '{{.Image}}' \"\$CID\" 2>/dev/null || echo '')
            if [ -n \"\$CIMG\" ] && ! docker image inspect \"\$CIMG\" >/dev/null 2>&1; then
                echo \"Container \$(docker inspect --format '{{.Name}}' \"\$CID\" 2>/dev/null) references a missing image, removing it so it can be recreated.\"
                docker rm -f \"\$CID\" >/dev/null
            fi
        done

        \$DOCKER_CMD up -d --no-deps --remove-orphans \$SERVICES
    "

    echo "--- Remote deployment completed successfully ---"
else
    echo "Error: Remote deployment skipped. No PORTAINER_WEBHOOK_URL, REMOTE_HOST, or SSH targets configured in .env."
    echo "To deploy locally, use 'docker compose up -d' or configure your remote target."
    exit 1
fi
