#!/bin/bash
set -e

# MuMaFi LMS Install Script
# Standardized interface for building, publishing, and deploying.

# Get the project root
ROOT_DIR="$(dirname "$(readlink -f "$0")")"
cd "$ROOT_DIR"

# Application-specific configuration
PROJECT_NAME="Lightweight Music Server"
AVAILABLE_APPS=("lms")
DEFAULT_APP="lms"

show_help() {
    echo "MuMaFi $PROJECT_NAME Install Script"
    echo "Usage: ./install.sh [options] [mode]"
    echo ""
    echo "Options:"
    echo "  --help          Show this help message"
    echo "  --remote        Offload build and publish to remote LXC"
    echo "  --app=<app>     Specify the application to install (default: $DEFAULT_APP)"
    echo "  --list          List available applications"
    echo ""
    echo "Modes:"
    echo "  debug           Build in debug mode (default)"
    echo "  release         Build in release mode"
    echo ""
    echo "Examples:"
    echo "  ./install.sh --remote release"
    echo "  ./install.sh --app=lms debug"
}

list_apps() {
    for app in "${AVAILABLE_APPS[@]}"; do
        echo "$app"
    done
}

# Default values
REMOTE=false
SELECTED_APPS=()
MODE=""

# Parse arguments
for i in "$@"; do
    case $i in
        --help)
            show_help
            exit 0
            ;;
        --remote)
            REMOTE=true
            ;;
        --list)
            list_apps
            exit 0
            ;;
        --app=*)
            SELECTED_APPS+=("${i#*=}")
            ;;
        debug|release)
            MODE="$i"
            ;;
        *)
            # Ignore other args or pass them through?
            ;;
    esac
done

# Validation and defaults
if [ ${#SELECTED_APPS[@]} -eq 0 ]; then
    SELECTED_APPS=("$DEFAULT_APP")
fi

if [ -z "$MODE" ]; then
    MODE="debug"
fi

# Build arguments for build_and_publish.sh
BP_ARGS=("$MODE")
if [ "$REMOTE" = true ]; then
    BP_ARGS+=("--remote")
fi

# For LMS, we just run the main script. 
# It currently doesn't support selective app building because there's only one.
./scripts/build_and_publish.sh "${BP_ARGS[@]}"
