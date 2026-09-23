#!/bin/bash
# scripts/ci/docker-hub-session.sh
#
# A Docker Hub login that ends with the job. Meant to be sourced.
#
# `docker login` writes the token into $DOCKER_CONFIG/config.json, which is
# ~/.docker/config.json of the runner account unless told otherwise. The runner
# is a shell executor shared by every pipeline, merge requests included, so a
# plain login left the push token of the muma account readable by any later
# job on that machine. docker_hub_login points DOCKER_CONFIG at a fresh private
# directory first; docker_hub_logout logs out and removes it. Callers run the
# logout from their EXIT trap. See
# docs/bug-reports/038-deploy-puts-every-prod-secret-on-the-command-line.md.

# docker_hub_login: log in to Docker Hub with DOCKERHUB_USERNAME/DOCKERHUB_TOKEN
# inside a throwaway DOCKER_CONFIG. The token goes in on stdin, never on argv.
docker_hub_login() {
    local home_config="${DOCKER_CONFIG:-$HOME/.docker}"
    local entry

    DOCKER_HUB_SESSION_DIR="$(mktemp -d)"
    chmod 700 "$DOCKER_HUB_SESSION_DIR"
    # CLI plugins (buildx among them) and builder/context state are looked up
    # under DOCKER_CONFIG too; link them so builds behave exactly as before.
    # None of these holds a credential -- those live in config.json alone.
    for entry in cli-plugins buildx contexts; do
        if [ -e "$home_config/$entry" ]; then
            ln -s "$home_config/$entry" "$DOCKER_HUB_SESSION_DIR/$entry"
        fi
    done
    export DOCKER_CONFIG="$DOCKER_HUB_SESSION_DIR"

    echo "--- Logging in to Docker Hub as ${DOCKERHUB_USERNAME} (session config, removed on exit) ---"
    printf '%s\n' "${DOCKERHUB_TOKEN}" | docker login --username "${DOCKERHUB_USERNAME}" --password-stdin
}

# docker_hub_logout: undo docker_hub_login. Safe to call when no login happened
# and safe to call twice.
docker_hub_logout() {
    if [ -z "${DOCKER_HUB_SESSION_DIR:-}" ]; then
        return 0
    fi
    docker logout >/dev/null 2>&1 || true
    # rm -rf removes the plugin symlinks themselves, never what they point at.
    rm -rf "$DOCKER_HUB_SESSION_DIR"
    unset DOCKER_HUB_SESSION_DIR DOCKER_CONFIG
}
