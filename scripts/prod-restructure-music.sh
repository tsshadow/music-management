#!/bin/bash
# scripts/prod-restructure-music.sh
#
# Runs the music folder restructure on the production host, end to end:
#
#     /mnt/music/EPs/<label>/<release>   ->  /mnt/music/labels/<label>/<release>
#     /mnt/music/EPs/__Free&None/...     ->  /mnt/music/songs/...
#     /mnt/music/EPs/__TODO/...          ->  /mnt/music/import/...
#     /mnt/music/Soundcloud/<channel>    ->  /mnt/music/channels/soundcloud/<channel>
#     /mnt/music/Youtube/<channel>       ->  /mnt/music/channels/youtube/<channel>
#
# EPs held three unrelated things: releases on a label, releases on none, and the intake pile. Only
# the first is a label tree, which is why the other two kept appearing in the label chart.
#
# It is five directory renames, not 326.480 file moves -- every move stays inside one mount, so each
# is a metadata operation, and --revert undoes it just as cheaply.
#
# Run it ON the production host, as root:
#
#     bash scripts/prod-restructure-music.sh --dry-run    # checks everything, changes nothing
#     bash scripts/prod-restructure-music.sh --apply
#     bash scripts/prod-restructure-music.sh --revert
#
# What it does, in order, and why that order:
#
#   1. Preflight. Every source must exist, every destination must be free, the database must answer,
#      and MariaDB's SHA2() must reproduce the hashes already stored -- see "the hash check" below.
#      Nothing is touched unless all of it passes: half a restructure is far worse than none.
#   2. Stops every container that has /mnt/music mounted, remembering which were running. A worker
#      writing into a folder that is being renamed is the one way to lose a file here.
#   3. Renames the five directories.
#   4. Rewrites the stored paths, and the hash derived from each, in the same statement.
#   5. Rewrites the four path settings in the stack's .env.
#   6. Starts back exactly the containers it stopped.
#
# The hash check. `library_media_files.file_path_hash` is the sha256 of the path, written by Python.
# This script recomputes it with MariaDB's SHA2(), so before changing anything it verifies that the
# two agree on rows that already exist. If they ever disagree -- a charset difference would do it --
# the script refuses rather than quietly filling the column with hashes the scanner will not
# recognise.
#
# What is deliberately not touched: ratings and listens. `rating_tracks.entity_id` is
# `library_tracks.track_uid`, derived from title, duration and primary artist, not from the path.
#
# Afterwards: LMS keys its own library on paths, so it needs a full rescan. And prod's .env is
# rewritten from the PROD_ENV_FILE CI/CD variable on every deploy -- update that variable too, or
# the next deploy puts the old paths back.

set -euo pipefail

MUSIC_ROOT="${MUSIC_ROOT:-/mnt/music}"
MODE=""

# source|destination, in the order they must happen: the two piles have to leave EPs before EPs
# itself is renamed, or they travel with it.
MOVES=(
    "EPs/__Free&None|songs"
    "EPs/__TODO|import"
    "EPs|labels"
    "Soundcloud|channels/soundcloud"
    "Youtube|channels/youtube"
)

# .env key|old value|new value, relative to MUSIC_ROOT.
ENV_KEYS=(
    "eps_folder_path|EPs|labels"
    "import_folder_path|EPs/__TODO|import"
    "soundcloud_folder|Soundcloud|channels/soundcloud"
    "youtube_folder|Youtube|channels/youtube"
)

usage() {
    sed -n '2,45p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
}

DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1; [ -n "$MODE" ] || MODE="dry-run" ;;
        --apply)   MODE="apply" ;;
        --revert)  MODE="revert" ;;
        *)         usage ;;
    esac
done
[ -n "$MODE" ] || usage
# `--revert --dry-run` reports what undoing would do, which is worth being able to read first.
# Written as an `if` rather than a `&&` chain: under `set -e` a chain whose first test fails is
# itself a failing command, and the script would exit here for the ordinary `--apply` case.
if [ "$DRY_RUN" -eq 1 ] && [ "$MODE" = "apply" ]; then
    MODE="dry-run"
fi

say()  { printf '%s\n' "$*"; }
step() { printf '\n=== %s ===\n' "$*"; }
die()  { printf 'REFUSING: %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "docker not found -- run this on the production host"

# ---------------------------------------------------------------------------
# Discovery: the database container, the stack's .env, and everything that
# holds /mnt/music open. All discovered rather than hardcoded, because the
# stack is Portainer-managed and its paths are not fixed.
# ---------------------------------------------------------------------------

step "Discovering the stack"

DB_CONTAINER="$(docker ps --format '{{.Names}}' \
    | while read -r name; do
        image="$(docker inspect "$name" --format '{{.Config.Image}}' 2>/dev/null || true)"
        case "$image" in *mariadb*|*mysql*) printf '%s\n' "$name" ;; esac
      done | head -n 1)"
[ -n "$DB_CONTAINER" ] || die "no MariaDB/MySQL container is running"
say "database container: $DB_CONTAINER"

# Every running container with /mnt/music mounted. These are the ones that could be mid-write.
MUSIC_CONTAINERS="$(docker ps --format '{{.Names}}' \
    | while read -r name; do
        if docker inspect "$name" --format '{{range .Mounts}}{{.Destination}} {{end}}' 2>/dev/null \
            | tr ' ' '\n' | grep -qx "/mnt/music"; then
            printf '%s\n' "$name"
        fi
      done)"
[ -n "$MUSIC_CONTAINERS" ] || say "warning: no running container has /mnt/music mounted"
say "containers holding /mnt/music:"
printf '  %s\n' $MUSIC_CONTAINERS

# The stack's .env, found from a container's compose labels. The compose files often sit in a
# subdirectory of the checkout while .env sits at its root, so the parent of each candidate is
# checked too. Set ENV_FILE=... to skip all of this.
ENV_FILE="${ENV_FILE:-}"
if [ -z "$ENV_FILE" ]; then
    for name in $MUSIC_CONTAINERS; do
        workdir="$(docker inspect "$name" \
            --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' 2>/dev/null || true)"
        config="$(docker inspect "$name" \
            --format '{{ index .Config.Labels "com.docker.compose.project.config_files" }}' 2>/dev/null | cut -d, -f1 || true)"
        for candidate in "$workdir" "$workdir/.." "$(dirname "${config:-/nonexistent}")" "$(dirname "${config:-/nonexistent}")/.."; do
            if [ -n "$candidate" ] && [ -f "$candidate/.env" ]; then
                ENV_FILE="$(cd "$candidate" && pwd)/.env"
                break 2
            fi
        done
    done
fi
if [ -n "$ENV_FILE" ]; then
    say "stack .env: $ENV_FILE"
else
    say "stack .env: NOT FOUND -- the four path settings will have to be changed by hand"
fi

DB_USER="${DB_USER:-root}"
DB_PASS="${DB_PASS:-}"
DB_NAME="${DB_NAME:-}"
if [ -n "$ENV_FILE" ]; then
    [ -n "$DB_PASS" ] || DB_PASS="$(grep -E '^MYSQL_ROOT_PASSWORD=' "$ENV_FILE" | head -n 1 | cut -d= -f2- || true)"
    [ -n "$DB_NAME" ] || DB_NAME="$(grep -E '^DB_DB=' "$ENV_FILE" | head -n 1 | cut -d= -f2- || true)"
fi
DB_NAME="${DB_NAME:-music-management}"
[ -n "$DB_PASS" ] || die "no database password -- set DB_PASS, or make MYSQL_ROOT_PASSWORD readable in ${ENV_FILE:-the stack .env}"
say "database name: $DB_NAME"

sql() {
    # MYSQL_PWD rather than -p: the client warns on every invocation about a password on the command
    # line, and that warning lands in the middle of output this script parses.
    #
    # No -i, and stdin closed: the query is passed with -e, so the client has no use for stdin --
    # and an interactive `docker exec` inside a `while read` loop swallows the rest of the loop's
    # input, which silently reduced a five-directory plan to its first entry.
    docker exec -e MYSQL_PWD="$DB_PASS" "$DB_CONTAINER" \
        mysql -u"$DB_USER" "$DB_NAME" -N -B -e "$1" < /dev/null
}

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

step "Preflight"

sql "SELECT 1" >/dev/null || die "cannot query the database"
say "database answers"

# The hash check: MariaDB must reproduce what Python wrote, or the rewrite would fill the column
# with values the scanner does not recognise and every file would look new.
MISMATCHED="$(sql "SELECT COUNT(*) FROM library_media_files WHERE file_path_hash <> SHA2(file_path, 256)")"
TOTAL_FILES="$(sql "SELECT COUNT(*) FROM library_media_files")"
say "media files: $TOTAL_FILES, stored hashes SHA2() cannot reproduce: $MISMATCHED"
[ "$MISMATCHED" = "0" ] || die "SHA2() does not reproduce $MISMATCHED stored hashes -- rewriting them here would break the scanner"

ordered_moves() {
    # Forward: as listed. Revert: reversed in direction and in order, so EPs exists again before
    # songs and import move back into it.
    if [ "$MODE" = "revert" ]; then
        for (( i=${#MOVES[@]}-1; i>=0; i-- )); do
            src="${MOVES[$i]%%|*}"; dst="${MOVES[$i]##*|}"
            printf '%s|%s\n' "$dst" "$src"
        done
    else
        printf '%s\n' "${MOVES[@]}"
    fi
}

PROBLEMS=0
while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    if [ ! -d "$MUSIC_ROOT/$src" ]; then
        say "  missing source: $MUSIC_ROOT/$src"; PROBLEMS=$((PROBLEMS+1))
    fi
    if [ -e "$MUSIC_ROOT/$dst" ]; then
        say "  destination already exists: $MUSIC_ROOT/$dst"; PROBLEMS=$((PROBLEMS+1))
    fi
done < <(ordered_moves)
[ "$PROBLEMS" -eq 0 ] || die "$PROBLEMS problem(s) -- the plan cannot be carried out in full"
say "all sources present, all destinations free"

step "Plan"
while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    # LEFT(...) rather than LIKE: '__Free&None' contains underscores, which are LIKE wildcards, and
    # '/mnt/music/EPs/__Free&None/%' would happily also match '/mnt/music/EPs/XXFree&None/...'.
    count="$(sql "SELECT COUNT(*) FROM library_media_files WHERE LEFT(file_path, CHAR_LENGTH('$MUSIC_ROOT/$src/')) = '$MUSIC_ROOT/$src/'")"
    say "  $MUSIC_ROOT/$src  ->  $MUSIC_ROOT/$dst    ($count media files)"
done < <(ordered_moves)

if [ -n "$ENV_FILE" ]; then
    for entry in "${ENV_KEYS[@]}"; do
        key="${entry%%|*}"; rest="${entry#*|}"
        old_rel="${rest%%|*}"; new_rel="${rest##*|}"
        if [ "$MODE" = "revert" ]; then tmp="$old_rel"; old_rel="$new_rel"; new_rel="$tmp"; fi
        current="$(grep -E "^${key}=" "$ENV_FILE" | head -n 1 | cut -d= -f2- || true)"
        say "  $key: ${current:-<unset>}  ->  $MUSIC_ROOT/$new_rel"
    done
fi

if [ "$MODE" = "dry-run" ] || [ "$DRY_RUN" -eq 1 ]; then
    say ""
    say "Dry run only. Nothing was stopped, moved or written."
    if [ "$MODE" = "revert" ]; then
        say "Re-run with --revert alone to perform it."
    else
        say "Re-run with --apply to perform it."
    fi
    exit 0
fi

say ""
printf 'This will stop the containers above, rename five directories and rewrite %s stored paths.\n' "$TOTAL_FILES"
printf 'Type "yes" to continue: '
read -r CONFIRM
[ "$CONFIRM" = "yes" ] || die "not confirmed"

# ---------------------------------------------------------------------------
# Do it
# ---------------------------------------------------------------------------

step "Stopping containers"
STOPPED=""
for name in $MUSIC_CONTAINERS; do
    say "  stopping $name"
    docker stop "$name" >/dev/null
    STOPPED="$STOPPED $name"
done

restart_containers() {
    step "Starting containers"
    for name in $STOPPED; do
        say "  starting $name"
        docker start "$name" >/dev/null || say "  WARNING: $name did not start"
    done
}
# Whatever happens next, the stack comes back up.
trap restart_containers EXIT

step "Renaming directories"
while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    mkdir -p "$(dirname "$MUSIC_ROOT/$dst")"
    mv "$MUSIC_ROOT/$src" "$MUSIC_ROOT/$dst"
    say "  $src -> $dst"
done < <(ordered_moves)

step "Rewriting stored paths"
while IFS='|' read -r src dst; do
    [ -n "$src" ] || continue
    old="$MUSIC_ROOT/$src/"
    new="$MUSIC_ROOT/$dst/"
    # file_path and file_path_hash in one statement: the hash is the sha256 of the path, so a row
    # with one updated and not the other is worse than a row with neither.
    sql "UPDATE library_media_files
         SET file_path = CONCAT('$new', SUBSTRING(file_path, CHAR_LENGTH('$old') + 1)),
             file_path_hash = SHA2(CONCAT('$new', SUBSTRING(file_path, CHAR_LENGTH('$old') + 1)), 256)
         WHERE LEFT(file_path, CHAR_LENGTH('$old')) = '$old'"
    moved="$(sql "SELECT COUNT(*) FROM library_media_files WHERE LEFT(file_path, CHAR_LENGTH('$new')) = '$new'")"
    say "  $dst: $moved media files"

    if [ "$(sql "SHOW TABLES LIKE 'tagger_processed_files'" | wc -l)" -gt 0 ]; then
        sql "UPDATE tagger_processed_files
             SET filepath = CONCAT('$new', SUBSTRING(filepath, CHAR_LENGTH('$old') + 1))
             WHERE LEFT(filepath, CHAR_LENGTH('$old')) = '$old'"
    fi
done < <(ordered_moves)

LEFTOVER="$(sql "SELECT COUNT(*) FROM library_media_files WHERE file_path_hash <> SHA2(file_path, 256)")"
[ "$LEFTOVER" = "0" ] || say "WARNING: $LEFTOVER rows now have a hash that does not match their path"

if [ -n "$ENV_FILE" ]; then
    step "Rewriting $ENV_FILE"
    BACKUP="$ENV_FILE.before-restructure.$(date +%Y%m%d%H%M%S)"
    cp "$ENV_FILE" "$BACKUP"
    say "  backup: $BACKUP"
    for entry in "${ENV_KEYS[@]}"; do
        key="${entry%%|*}"; rest="${entry#*|}"
        old_rel="${rest%%|*}"; new_rel="${rest##*|}"
        if [ "$MODE" = "revert" ]; then tmp="$old_rel"; old_rel="$new_rel"; new_rel="$tmp"; fi
        value="$MUSIC_ROOT/$new_rel"
        if grep -qE "^${key}=" "$ENV_FILE"; then
            sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
        else
            printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
        fi
        say "  $key=$value"
    done
fi

trap - EXIT
restart_containers

step "Done"
say "Still to do, and neither is optional:"
say "  1. Full LMS rescan. It keys its own library on paths, and every path just changed."
say "  2. Update the PROD_ENV_FILE CI/CD variable with the four new paths. Prod's .env is"
say "     rewritten from it on every deploy, so without this the next deploy undoes step 5."
if [ "$MODE" = "apply" ]; then
    say ""
    say "To undo: bash $0 --revert"
fi
