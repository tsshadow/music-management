#!/bin/bash
# scripts/ci/prune-prod-images.sh
#
# Removes the Docker images on the production host that nothing needs any more,
# after a deploy has been verified.
#
# Why: every release and hotfix deploy pulls a fresh set of images and nothing
# ever removed the old ones. On 2026-09-26 the host's root disk was 95% full
# (5.5 GB free of 99 GB) with 377 images, 61 of their 67 GB reclaimable; five
# deploys had landed on 2026-09-25 alone. A full disk on this host has presented
# as an unrelated 502 before. See docs/bug-reports/094-deploy-image-prune-and-db-safety.md.
#
# What it keeps (the decision lives in prod_image_prune_plan.py, a pure function
# with its own tests):
#   - every image a container uses, running or stopped;
#   - per repository, the PRUNE_KEEP_RELEASES (default 3) most recently built
#     images no container uses: the previous releases the IMAGE_TAG rollback
#     lever redeploys (docs/deployment.md#rollback);
#   - anything tagged :latest, :stable or :rc (the nightly db-backup runs
#     muma-tools:latest with `run --rm`, so no container holds it in between).
#
# How: `docker rmi` without -f, one reference at a time. Without -f Docker
# refuses to remove an image a container uses, which is the interlock should a
# container start between the listing and the removal. A reference that cannot
# be removed is reported and skipped; pruning never fails a deploy that worked.
# Free space on / is logged before and after.
#
# Called by ci-deploy.sh once post-deploy-verify.sh has passed -- never before:
# until the new release is verified, the images it replaced are the way back.
# Also safe to run by hand from a machine with the production ssh key:
#   REMOTE_HOST=192.0.2.27 REMOTE_USER=root ./scripts/ci/prune-prod-images.sh
#
# Knobs: PRUNE_KEEP_RELEASES=3, PRUNE_IMAGES=0 (skip entirely),
#        PRUNE_DRY_RUN=1 (list what would go, remove nothing).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ "${PRUNE_IMAGES:-1}" = "0" ]; then
    echo "--- PRUNE_IMAGES=0: leaving the production images alone ---"
    exit 0
fi

KEEP="${PRUNE_KEEP_RELEASES:-3}"
case "$KEEP" in
    ''|*[!0-9]*|0) echo "Error: PRUNE_KEEP_RELEASES must be a whole number of at least 1."; exit 1 ;;
esac

# Same ssh setup as post-deploy-verify.sh: standalone it sets up its own agent,
# from ci-deploy.sh it inherits one but not the PROD_SSH_OPTS array.
if [ -z "${REMOTE_HOST}" ]; then
    # shellcheck source=scripts/ci/prod-ssh-setup.sh
    . "$SCRIPT_DIR/prod-ssh-setup.sh"
fi
if [ "${#PROD_SSH_OPTS[@]}" -eq 0 ]; then
    # shellcheck source=scripts/lib/ssh_host_keys.sh
    . "$PROJECT_ROOT/scripts/lib/ssh_host_keys.sh"
    ssh_host_key_opts_into PROD_SSH_OPTS "$REMOTE_HOST" || exit 1
fi

# remote CMD: run CMD on the production host, with this shell's stdin.
remote() {
    ssh "${PROD_SSH_OPTS[@]}" "${REMOTE_USER}@${REMOTE_HOST}" "$@"
}

FREE_CMD="df -Pk / | awk 'NR == 2 { printf \"%.1f GB free on / (%s used)\", \$4 / 1048576, \$5 }'"

echo "--- Pruning unused images on $REMOTE_HOST (keeping $KEEP previous per repository) ---"
echo "Before: $(remote "$FREE_CMD")"

# One inspect template instead of `docker image ls`: an image whose tag moved on
# keeps its repository only in RepoDigests, and whether `image ls` shows it
# there depends on the Docker version and image store.
LISTING="$(remote "
    set -e
    docker ps -aq | xargs -r docker inspect --format 'container	{{.Image}}'
    docker image ls -q --no-trunc | sort -u | xargs -r docker image inspect --format 'image	{{.Id}}	{{.Created}}{{range .RepoTags}}{{println}}tag	{{\$.Id}}	{{.}}{{end}}{{range .RepoDigests}}{{println}}digest	{{\$.Id}}	{{.}}{{end}}'
")"

REMOVALS="$(printf '%s\n' "$LISTING" | python3 "$SCRIPT_DIR/prod_image_prune_plan.py" --keep "$KEEP")"

if [ -z "$REMOVALS" ]; then
    echo "Nothing to remove."
    exit 0
fi

if [ "${PRUNE_DRY_RUN:-0}" = "1" ]; then
    echo "PRUNE_DRY_RUN=1, would remove:"
    printf '  %s\n' $REMOVALS
    exit 0
fi

# The references travel on stdin, one per line, and are only ever expanded in
# double quotes on the host: nothing in an image name reaches a shell as code.
printf '%s\n' "$REMOVALS" | remote "
    removed=0
    failed=0
    while IFS= read -r ref; do
        [ -n \"\$ref\" ] || continue
        if out=\$(docker rmi \"\$ref\" 2>&1); then
            echo \"removed \$ref\"
            removed=\$((removed + 1))
        else
            echo \"skipped \$ref: \$(printf '%s' \"\$out\" | tail -n 1)\"
            failed=\$((failed + 1))
        fi
    done
    echo \"\$removed reference(s) removed, \$failed skipped.\"
"

echo "After: $(remote "$FREE_CMD")"
