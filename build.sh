#!/bin/bash
# .env values are read the way docker-compose reads them (a `#` inside a
# value is not a comment); see scripts/lib/dotenv.sh and bug report 038.
# shellcheck source=scripts/lib/dotenv.sh
. "$(dirname "${BASH_SOURCE[0]}")/scripts/lib/dotenv.sh"
set -e

# Check for docker permissions
if ! docker info >/dev/null 2>&1; then
    if [ -z "$DOCKER_GROUP_RETRY" ] && getent group docker | grep -q "\b$USER\b"; then
        export DOCKER_GROUP_RETRY=1
        echo "Detected 'docker' group membership but it's not active in this session."
        echo "Re-executing with 'sg docker'..."
        CMD=$(printf "%q " "$0" "$@")
        exec sg docker -c "$CMD"
    fi
    echo "ERROR: Permission denied while trying to connect to the Docker daemon."
    echo "Please ensure your user ($USER) is in the 'docker' group."
    echo "You can add yourself with: sudo usermod -aG docker \$USER"
    echo "Then log out and log back in, or run: newgrp docker"
    exit 1
fi

    echo "--- Starting build of containers ---"
    
    DEBUG_MODE=false
    REMOTE_MODE=false
    SEMI_REMOTE_MODE=false
    SKIP_LINT=false
    SKIP_TEST=false
    for arg in "$@"; do
        if [ "$arg" == "--debug" ]; then
            DEBUG_MODE=true
        elif [ "$arg" == "--remote" ]; then
            REMOTE_MODE=true
        elif [ "$arg" == "--semi-remote" ]; then
            SEMI_REMOTE_MODE=true
        elif [ "$arg" == "--skip-lint" ]; then
            SKIP_LINT=true
        elif [ "$arg" == "--skip-test" ]; then
            SKIP_TEST=true
        fi
    done

    if [ "$REMOTE_MODE" = true ] && [ "$SEMI_REMOTE_MODE" = true ]; then
        echo "ERROR: Cannot use both --remote and --semi-remote"
        exit 1
    fi

    if [ "$DEBUG_MODE" = true ]; then
        echo "--- Debug mode enabled ---"
        set -x
    fi

if [ -f .env ]; then
    dotenv_load .env
fi

# Also load services/music-management-server/.env, which holds
# VITE_GOOGLE_CLIENT_ID (the frontend build-arg counterpart of the root
# .env's GOOGLE_CLIENT_ID). See docs/deployment.md.
if [ -f services/music-management-server/.env ]; then
    dotenv_load services/music-management-server/.env
fi

# Configuration
DOCKER_USER="${DOCKER_USER}"
IMAGE_ML="${IMAGE_ML}"
IMAGE_CORE="music-manager"
IMAGE_TOOLS="${IMAGE_TOOLS}"
IMAGE_APP="${IMAGE_APP}"
IMAGE_BASE="${IMAGE_BASE}"
IMAGE_DOWNLOADER="${IMAGE_DOWNLOADER}"
IMAGE_TELEGRAM="${IMAGE_TELEGRAM}"
IMAGE_IMPORTER="${IMAGE_IMPORTER}"
IMAGE_SERVER="music-management-server"
VERSION=$(cat VERSION 2>/dev/null || echo "latest")

# Docker command configuration
DOCKER_CMD="docker"
if [ "$REMOTE_MODE" = true ] || [ "$SEMI_REMOTE_MODE" = true ]; then
    export DOCKER_FLAGS="--network host"
fi

#if [ "$REMOTE_MODE" = true ]; then
#    echo "--- Remote build mode enabled ---"
#    DOCKER_CMD="docker -c remote-lxc"
#fi

build_base() {
    echo "--- Building Base Image ($VERSION) ---"
    $DOCKER_CMD build $DOCKER_FLAGS -t "${DOCKER_USER}/${IMAGE_BASE}:latest" -t "${DOCKER_USER}/${IMAGE_BASE}:${VERSION}" -f docker/Dockerfile.base .
}

build_downloader() {
    echo "--- Building Downloader ($VERSION) ---"
    $DOCKER_CMD build $DOCKER_FLAGS --build-arg DOCKER_USER="${DOCKER_USER}" --build-arg VERSION="${VERSION}" -t "${DOCKER_USER}/${IMAGE_DOWNLOADER}:latest" -t "${DOCKER_USER}/${IMAGE_DOWNLOADER}:${VERSION}" -f docker/Dockerfile.downloader .
}

build_telegram() {
    echo "--- Building Telegram ($VERSION) ---"
    $DOCKER_CMD build $DOCKER_FLAGS --build-arg DOCKER_USER="${DOCKER_USER}" --build-arg VERSION="${VERSION}" -t "${DOCKER_USER}/${IMAGE_TELEGRAM}:latest" -t "${DOCKER_USER}/${IMAGE_TELEGRAM}:${VERSION}" -f docker/Dockerfile.telegram .
}

build_importer() {
    echo "--- Building Importer ($VERSION) ---"
    $DOCKER_CMD build $DOCKER_FLAGS --build-arg DOCKER_USER="${DOCKER_USER}" --build-arg VERSION="${VERSION}" -t "${DOCKER_USER}/${IMAGE_IMPORTER}:latest" -t "${DOCKER_USER}/${IMAGE_IMPORTER}:${VERSION}" -f docker/Dockerfile.importer .
}

# Deprecated and disabled (services/ml-analyzer/DEPRECATED.md): not part of the
# build-all run below, only built when `ml` is asked for by name.
build_ml() {
    local cmd=$DOCKER_CMD
    echo "WARNING: ml-analyzer is deprecated and not deployed -- see services/ml-analyzer/DEPRECATED.md"
    if [ "$SEMI_REMOTE_MODE" = true ]; then cmd="docker -c remote-lxc"; fi
    echo "--- Building ML Analyzer ($VERSION) ---"
    $cmd build $DOCKER_FLAGS -t "${DOCKER_USER}/${IMAGE_ML}:latest" -t "${DOCKER_USER}/${IMAGE_ML}:${VERSION}" -f services/ml-analyzer/Dockerfile .
}

build_tools() {
    local cmd=$DOCKER_CMD
    if [ "$SEMI_REMOTE_MODE" = true ]; then cmd="docker -c remote-lxc"; fi
    echo "--- Building Tools ($VERSION) ---"
    $cmd build $DOCKER_FLAGS -t "${DOCKER_USER}/${IMAGE_TOOLS}:latest" -t "${DOCKER_USER}/${IMAGE_TOOLS}:${VERSION}" -f docker/Dockerfile.tools .
}


build_manager() {
    echo "--- Building Music Manager ($VERSION) ---"
    $DOCKER_CMD build $DOCKER_FLAGS --build-arg DOCKER_USER="${DOCKER_USER}" --build-arg VERSION="${VERSION}" -t "${DOCKER_USER}/${IMAGE_CORE}:latest" -t "${DOCKER_USER}/${IMAGE_CORE}:${VERSION}" -f docker/Dockerfile.music-manager .
}

build_server() {
    echo "--- Building Music Management Server ($VERSION) ---"
    $DOCKER_CMD build $DOCKER_FLAGS --build-arg VITE_GOOGLE_CLIENT_ID="${VITE_GOOGLE_CLIENT_ID}" -t "${DOCKER_USER}/${IMAGE_SERVER}:latest" -t "${DOCKER_USER}/${IMAGE_SERVER}:${VERSION}" -f services/music-management-server/Dockerfile-release .
}

run_linter() {
    echo "--- Running pylint ---"
    if ! python3 -m pylint services/ --fail-under=8.5; then
        echo ""
        echo "❌ ERROR: Pylint score too low! Build aborted."
        exit 1
    fi
    echo "--- Pylint passed ---"
}

run_tests() {
    echo "--- Running tests ---"
    PYTHONPATH=$PYTHONPATH:$(pwd)
    export PYTHONPATH
    # Focus on downloader and importer tests as requested
    TEST_TARGETS="services/downloader/soundcloud/tests/ services/importer/tests/ services/tests/YoutubeDownloaderTest.py services/music_manager/tests/"
    if ! python3 -m pytest -p no:warnings $TEST_TARGETS; then
        echo ""
        echo "❌ ERROR: Tests failed! Build aborted."
        exit 1
    fi
    echo "--- Tests passed ---"
}

# Filter arguments to remove special flags
REQUESTED_MODULES=()
for arg in "$@"; do
    case $arg in
        --debug|--remote|--semi-remote|--skip-lint|--skip-test|patch) ;;
        *) REQUESTED_MODULES+=("$arg") ;;
    esac
done

if [ "$SEMI_REMOTE_MODE" = true ]; then
    echo "--- Semi-remote build mode enabled ---"
    echo "--- Building ML, Tools, and Manager remote, others local ---"
fi

# All builds require passing tests and linting (unless skipped)
if [ "$SKIP_LINT" = false ]; then
    run_linter
else
    echo "--- Skipping pylint ---"
fi

if [ "$SKIP_TEST" = false ]; then
    run_tests
else
    echo "--- Skipping tests ---"
fi

if [ ${#REQUESTED_MODULES[@]} -eq 0 ]; then
    echo "--- Building all modules in parallel ---"
    # Group 1: Independent builds. The ml-analyzer image is left out on
    # purpose: it is deprecated (services/ml-analyzer/DEPRECATED.md).
    build_tools &
    
    # Group 2: Base-dependent builds
    build_base
    
    build_manager &
    build_server &
    build_downloader &
    build_telegram &
    build_importer &
    
    wait
else
    echo "--- Building requested modules: ${REQUESTED_MODULES[*]} ---"
    # If base is needed by any of the requested modules, build it once first
    NEED_BASE=false
    for arg in "${REQUESTED_MODULES[@]}"; do
        case $arg in
            downloader|telegram|importer|base) NEED_BASE=true ;;
        esac
    done
    
    if [ "$NEED_BASE" = true ]; then
        build_base
    fi

    for arg in "${REQUESTED_MODULES[@]}"; do
        case $arg in
            ml) build_ml & ;;
            tools) build_tools & ;;
            lms|server|music-management-server) build_server & ;;
            manager|music-manager) build_manager & ;;
            downloader) build_downloader & ;;
            telegram) build_telegram & ;;
            importer) build_importer & ;;
            base) ;; # Already built if needed
            *) echo "Unknown component: $arg"; exit 1 ;;
        esac
    done
    wait
fi

echo "--- Build process completed ---"
