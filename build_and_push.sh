#!/bin/bash
set -e

echo "--- Starting build and push of ALL containers ---"

# Call individual scripts
./build_push_ml_analyzer.sh
./build_push_tools.sh
./build_push_app.sh

echo "--- All builds and pushes completed ---"
