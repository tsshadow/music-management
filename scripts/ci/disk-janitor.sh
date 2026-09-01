#!/bin/bash
# scripts/ci/disk-janitor.sh
# Reclaims disk on a CI runner by removing Docker image tags nothing needs.
#
# Both runners fill up every few weeks and then break jobs that have nothing
# wrong with them: on 2026-08-31 the LXC hit 96% and took out four jobs, three
# of which reported "no matching files" on artifact upload rather than anything
# about disk. The fix has always been the same handful of `docker rmi` calls,
# run by hand after the fact. This script is that recipe, so it can run before
# the fact.
#
# What it removes (the selection itself lives in disk_janitor_plan.py):
#   - muma/* and muma-ci/* per-version tags, keeping the 3 newest per
#     repository plus :latest and :stable. All recoverable from Docker Hub.
#   - music-management/android-ci:<hash>, keeping the 2 newest (>5GB each).
#   - muma-test-<job-id>-* leftovers older than two hours.
#   - Dangling (untagged) images, via `docker image prune`.
#
# What it deliberately does NOT touch:
#   - The buildkit build cache. That is the ccache keeping server:unit at
#     ~90s instead of ~405s, and pruning it is the tempting mistake this note
#     has now watched two people make (one of them me).
#   - Third-party images (mariadb, phpmyadmin, trivy, gitleaks, ...). They cost
#     a re-pull and free little.
#   - Anything, via `docker rmi -f`. Without -f, an image whose container still
#     exists is refused, which is the interlock that makes this safe to run
#     while other pipelines are working.
#
# Usage:
#   ./scripts/ci/disk-janitor.sh                 # sweep only if above 75%
#   ./scripts/ci/disk-janitor.sh --dry-run       # print the plan, remove nothing
#   ./scripts/ci/disk-janitor.sh --force         # sweep regardless of usage
#   ./scripts/ci/disk-janitor.sh --threshold 60  # different trigger point
#
# Exit codes:
#   0  nothing to do, or the sweep finished
#   1  the disk is still critically full afterwards -- a human is needed
#   2  Docker is not usable here

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

THRESHOLD=75
# Swept down to this rather than to the threshold, so a runner sitting just
# above the line does not sweep a single image every time the timer fires.
TARGET=65
# Above this after a full sweep, tags are no longer the problem: it is the
# build cache, a runaway build directory or something outside Docker entirely.
CRITICAL=85
# The normal pass is deliberately gentle: an evicted android-ci image costs a
# ~10 minute rebuild and an evicted version tag a pull, and on a host that is
# merely above the threshold that is a bad trade. The escalation pass runs when
# the host is still critical afterwards, where the trade reverses -- and it also
# keeps the "tags are no longer the problem" message below honest, which it was
# not while a 9GB image sat there protected by policy rather than by safety.
#
# Do not size the win from `docker images`: two android-ci tags each reported
# 17.1GB and removing one freed nothing, because they differ by one apt layer
# and the column counts shared layers per tag. That is the same double-count
# that makes `docker system df` promise 73GB and deliver 13GB.
KEEP_VERSIONS=3
KEEP_ANDROID=2
ESCALATED_KEEP_VERSIONS=1
ESCALATED_KEEP_ANDROID=1
DRY_RUN=0
FORCE=0

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --force) FORCE=1; shift ;;
        --threshold) THRESHOLD="$2"; shift 2 ;;
        --target) TARGET="$2"; shift 2 ;;
        --critical) CRITICAL="$2"; shift 2 ;;
        --keep-versions) KEEP_VERSIONS="$2"; shift 2 ;;
        --keep-android) KEEP_ANDROID="$2"; shift 2 ;;
        -h|--help) sed -n '2,40p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    echo "Error: no usable Docker daemon here." >&2
    exit 2
fi

DOCKER_ROOT="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null)"
[ -d "${DOCKER_ROOT:-}" ] || DOCKER_ROOT=/

usage_percent() {
    df -P "$DOCKER_ROOT" | awk 'NR==2 {gsub(/%/, "", $5); print $5}'
}

human_free() {
    df -Ph "$DOCKER_ROOT" | awk 'NR==2 {print $4 " free of " $2}'
}

BEFORE="$(usage_percent)"
echo "--- Disk janitor on $(hostname): ${DOCKER_ROOT} at ${BEFORE}% ($(human_free)) ---"

if [ "$BEFORE" -lt "$THRESHOLD" ] && [ "$FORCE" -eq 0 ]; then
    echo "Below the ${THRESHOLD}% threshold; nothing to do."
    exit 0
fi

removed=0
refused=0

plan_for() {
    # $1: keep-versions, $2: keep-android
    docker images --format '{{.Repository}}:{{.Tag}}	{{.CreatedAt}}	{{.ID}}' \
        | python3 "$SCRIPT_DIR/disk_janitor_plan.py" \
              --keep-versions "$1" --keep-android "$2"
}

sweep() {
    # $1: newline-separated image refs, oldest first.
    local checked=0 current
    while IFS= read -r image; do
        [ -n "$image" ] || continue
        if docker rmi "$image" >/dev/null 2>&1; then
            removed=$((removed + 1))
            echo "removed $image"
        else
            # Almost always "image is being used by container", which is the
            # interlock doing its job on a stack another pipeline still holds.
            refused=$((refused + 1))
        fi
        checked=$((checked + 1))
        if [ $((checked % 10)) -eq 0 ]; then
            current="$(usage_percent)"
            if [ "$current" -le "$TARGET" ]; then
                echo "--- Down to ${current}%, stopping early and keeping the rest ---"
                return 0
            fi
        fi
    done <<< "$1"
}

PLAN="$(plan_for "$KEEP_VERSIONS" "$KEEP_ANDROID")"

if [ "$DRY_RUN" -eq 1 ]; then
    echo "--- Normal pass would remove: ---"
    printf '%s\n' "${PLAN:-(nothing)}"
    echo "--- Escalation pass (only if still >=${CRITICAL}%) would additionally remove: ---"
    comm -13 <(printf '%s\n' "$PLAN" | sort) \
             <(plan_for "$ESCALATED_KEEP_VERSIONS" "$ESCALATED_KEEP_ANDROID" | sort)
    echo "--- Dry run: nothing was removed ---"
    exit 0
fi

if [ -n "$PLAN" ]; then
    echo "--- $(printf '%s\n' "$PLAN" | wc -l) removable image tags, oldest first ---"
    sweep "$PLAN"
fi

# Escalation. The conservative keep-counts above exist to protect build speed:
# an evicted android-ci image costs a ~10 minute rebuild, an evicted version tag
# a pull. Both are cheaper than a full disk, so once we are still critical those
# reasons stop outweighing the disk -- and saying "tags are no longer the
# problem" while a 9GB android image sits there protected by policy would simply
# be false. Everything here is still recoverable and still never forced.
if [ "$(usage_percent)" -ge "$CRITICAL" ]; then
    ESCALATED="$(comm -13 <(printf '%s\n' "$PLAN" | sort) \
                          <(plan_for "$ESCALATED_KEEP_VERSIONS" "$ESCALATED_KEEP_ANDROID" | sort))"
    if [ -n "$ESCALATED" ]; then
        echo "--- Still at $(usage_percent)%: escalating to keep-versions=${ESCALATED_KEEP_VERSIONS}, keep-android=${ESCALATED_KEEP_ANDROID} ---"
        # Re-sorted oldest-first by the planner, so re-plan rather than reuse
        # the set-difference order.
        sweep "$(plan_for "$ESCALATED_KEEP_VERSIONS" "$ESCALATED_KEEP_ANDROID")"
    fi
fi

# Dangling images only (no -a): layers orphaned by the removals above and by
# interrupted builds. Never `prune -a`, which would take the third-party images
# this script deliberately leaves alone.
docker image prune -f >/dev/null 2>&1

AFTER="$(usage_percent)"
echo "--- Removed $removed tags, $refused refused (in use); ${BEFORE}% -> ${AFTER}% ($(human_free)) ---"

if [ "$AFTER" -ge "$CRITICAL" ]; then
    echo ""
    echo "Still at ${AFTER}% after the escalated sweep. Tags are no longer the problem" >&2
    echo "-- everything this script may remove is gone." >&2
    echo "Look at the build cache size (docker system df), the runner's build" >&2
    echo "directories, and anything outside Docker. Pruning the build cache" >&2
    echo "works but costs the server:unit ccache -- decide that knowingly." >&2
    exit 1
fi

exit 0
