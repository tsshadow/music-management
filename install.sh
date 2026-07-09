+#!/bin/bash

set -e

# MuMaFi Music Management Install Script
# Standardized interface for building, publishing, and deploying.

# Get the project root
ROOT_DIR="$(dirname "$(readlink -f "$0")")"
cd "$ROOT_DIR"

# Application-specific configuration
PROJECT_NAME="Music Management"
AVAILABLE_APPS=("ml" "tools" "app" "manager" "management" "scanner" "tagger" "downloader" "telegram" "importer" "rating" "scrobble" "user" "stats")

show_help() {
    echo "MuMaFi $PROJECT_NAME Install Script"
    echo "Usage: ./install.sh [options] [apps...]"
    echo ""
    echo "Options:"
    echo "  --help          Show this help message"
    echo "  --remote        Offload build and publish to remote LXC"
    echo "  --semi-remote   Use semi-remote mode (heavy images remote, others local)"
    echo "  --all           Force build and publish of all applications"
    echo "  --debug         Enable debug output"
    echo "  --app=<app>     Specify an application to install"
    echo "  --list          List available applications"
    echo "  --show-stats    Show music library statistics (CLI)"
    echo ""
    echo "Apps:"
    for app in "${AVAILABLE_APPS[@]}"; do
        echo "  $app"
    done
    echo ""
    echo "Examples:"
    echo "  ./install.sh --remote user rating"
    echo "  ./install.sh --app=user --app=rating"
    echo "  ./install.sh --semi-remote app"
}

list_apps() {
    for app in "${AVAILABLE_APPS[@]}"; do
        echo "$app"
    done
}

# Default values
REMOTE_FLAG=""
DEBUG_FLAG=""
SELECTED_APPS=()

# Parse arguments
for i in "$@"; do
    case $i in
        --help)
            show_help
            exit 0
            ;;
        --remote)
            REMOTE_FLAG="--remote"
            ;;
        --semi-remote)
            REMOTE_FLAG="--semi-remote"
            ;;
        --all)
            SELECTED_APPS=("all")
            ;;
        --debug)
            DEBUG_FLAG="--debug"
            ;;
        --list)
            list_apps
            exit 0
            ;;
        --show-stats)
            python3 scripts/library_stats.py
            exit 0
            ;;
        --app=*)
            SELECTED_APPS+=("${i#*=}")
            ;;
        -*)
            # Ignore other flags
            ;;
        *)
            # Positional arguments are treated as app names
            SELECTED_APPS+=("$i")
            ;;
    esac
done

# Check for docker permissions
if ! docker info >/dev/null 2>&1; then
    if [ -z "$DOCKER_GROUP_RETRY" ] && getent group docker | grep -q "\b$USER\b"; then
        export DOCKER_GROUP_RETRY=1
        echo "Detected 'docker' group membership but it's not active in this session."
        echo "Re-executing with 'sg docker'..."
        CMD=$(printf "%q " "$0" "$@")
        exec sg docker -c "$CMD"
    fi
fi

# Detect affected modules if none selected
if [ ${#SELECTED_APPS[@]} -eq 0 ]; then
    chmod +x scripts/affected.sh
    AFFECTED=$(./scripts/affected.sh)
    
    if [ "$AFFECTED" == "none" ]; then
        echo "No changes detected. Skipping build and publish."
        exit 0
    fi
    
    if [ "$AFFECTED" == "all" ]; then
        echo "Global changes detected. Building all modules."
    else
        echo "Affected modules: $AFFECTED"
        # Split AFFECTED into SELECTED_APPS array
        read -r -a SELECTED_APPS <<< "$AFFECTED"
    fi
elif [ "${SELECTED_APPS[0]}" == "all" ]; then
    echo "Forcing build of all modules."
    SELECTED_APPS=() # Empty SELECTED_APPS means all in build.sh/publish.sh
fi

# Construct arguments for sub-scripts
BP_ARGS=()
[ -n "$REMOTE_FLAG" ] && BP_ARGS+=("$REMOTE_FLAG")
[ -n "$DEBUG_FLAG" ] && BP_ARGS+=("$DEBUG_FLAG")
[ ${#SELECTED_APPS[@]} -gt 0 ] && BP_ARGS+=("${SELECTED_APPS[@]}")

# Execute stages
echo "--- Starting MuMaFi Install Process ---"
./build.sh "${BP_ARGS[@]}"
./publish.sh "${BP_ARGS[@]}"
./scripts/deploy.sh "${BP_ARGS[@]}"

echo "Install completed successfully!"
