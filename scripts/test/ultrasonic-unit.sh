#!/bin/bash
# scripts/test/ultrasonic-unit.sh
# Runs Android unit tests with Jacoco coverage inside a Docker container.

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "--- Running Ultrasonic Android unit tests with coverage (via Docker) ---"

# We use a docker image with Android SDK to avoid installing it on the runner.
# We mount the root dir to /workspace and run from services/ultrasonic.
# Note: we use --user to ensure files created in the volume are owned by the host user.
docker run --rm \
    -v "$ROOT_DIR:/workspace" \
    -w "/workspace/services/ultrasonic" \
    -e SIGNING_STORE_PASSWORD=dummy \
    -e SIGNING_KEY_ALIAS=dummy \
    -e SIGNING_KEY_PASSWORD=dummy \
    mobiledevops/android-sdk-image:latest \
    ./gradlew :ultrasonic:jacocoTestReport

# Extract and fix the report
REPORT_SRC="services/ultrasonic/ultrasonic/build/reports/jacoco/jacocoTestReport/jacocoTestReport.xml"
REPORT_DEST="cobertura-ultrasonic.xml"

if [ -f "$ROOT_DIR/$REPORT_SRC" ]; then
    echo "--- Fixing paths in $REPORT_DEST ---"
    cp "$ROOT_DIR/$REPORT_SRC" "$ROOT_DIR/$REPORT_DEST"
    # Jacoco XML: filename="org/moire/ultrasonic/SomeFile.kt"
    # Repo path: services/ultrasonic/ultrasonic/src/main/kotlin/org/moire/ultrasonic/SomeFile.kt
    sed -i 's|filename="|filename="services/ultrasonic/ultrasonic/src/main/kotlin/|g' "$ROOT_DIR/$REPORT_DEST"
    sed -i 's|<source>.*</source>|<source>./</source>|g' "$ROOT_DIR/$REPORT_DEST"
else
    echo "❌ ERROR: Coverage report not found at $REPORT_SRC"
    # List files to help debugging if it fails
    find services/ultrasonic -name "*.xml" | grep jacoco || true
    exit 1
fi

echo "--- Ultrasonic unit tests passed and coverage extracted ---"
