#!/bin/bash
set -e

# MuMaFi Music Management Install Script
# Standardized interface for building, publishing, and deploying.

# Get the project root
ROOT_DIR="$(dirname "$(readlink -f "$0")")"
cd "$ROOT_DIR"

# Application-specific configuration
PROJECT_NAME="Music Management"
AVAILABLE_APPS=("ml" "tools" "app" "management" "scanner" "tagger" "downloader" "telegram" "importer" "rating" "scrobble" "user")

show_help() {
    echo "MuMaFi $PROJECT_NAME Install Script"
    echo "Usage: ./install.sh [options] [apps...]"
    echo ""
    echo "Options:"
    echo "  --help          Show this help message"
    echo "  --remote        Offload build and publish to remote LXC"
    echo "  --semi-remote   Use semi-remote mode (heavy images remote, others local)"
    echo "  --app=<app>     Specify an application to install"
    echo "  --list          List available applications"
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
        --list)
            list_apps
            exit 0
            ;;
        --app=*)
            SELECTED_APPS+=("${i#*=}")
            ;;
        -*)
            # Ignore other flags for now
            ;;
        *)
            # Positional arguments are treated as app names
            SELECTED_APPS+=("$i")
            ;;
    esac
done

BP_ARGS=()
if [ -n "$REMOTE_FLAG" ]; then
    BP_ARGS+=("$REMOTE_FLAG")
fi

if [ ${#SELECTED_APPS[@]} -gt 0 ]; then
    BP_ARGS+=("${SELECTED_APPS[@]}")
fi

./build_and_publish.sh "${BP_ARGS[@]}"
