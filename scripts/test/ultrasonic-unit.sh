#!/bin/bash
# scripts/test/ultrasonic-unit.sh
# Runs Android unit tests with Jacoco coverage inside a Docker container.

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

echo "--- Running Ultrasonic Android unit tests with coverage (via Docker) ---"

# Ensure the gradle home directory exists and is writable
mkdir -p "$ROOT_DIR/services/ultrasonic/.gradle_home"
chmod -R 777 "$ROOT_DIR/services/ultrasonic/.gradle_home"

# We use a docker image with Android SDK to avoid installing it on the runner.
# We run as root and then fix permissions for the host.
docker run --rm \
    -v "$ROOT_DIR:/workspace" \
    -w "/workspace/services/ultrasonic" \
    -e GRADLE_USER_HOME="/workspace/services/ultrasonic/.gradle_home" \
    -e SIGNING_STORE_PASSWORD=dummy \
    -e SIGNING_KEY_ALIAS=dummy \
    -e SIGNING_KEY_PASSWORD=dummy \
    mobiledevops/android-sdk-image:34 \
    ./gradlew :ultrasonic:jacocoTestReport

# Fix permissions for files created by root in the container
docker run --rm -v "$ROOT_DIR:/workspace" alpine chown -R "$(id -u):$(id -g)" /workspace

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
    
    # Print summary for GitLab coverage regex parsing
    python3 -c "import xml.etree.ElementTree as ET; tree = ET.parse('$ROOT_DIR/$REPORT_DEST'); root = tree.getroot(); \
        c = [cnt for cnt in root.findall('counter') if cnt.get('type') == 'LINE'][0]; \
        cov = int(c.get('covered')); total = cov + int(c.get('missed')); \
        print(f'Total Jacoco Line Coverage: {100*cov/total:.2f}%')"
else
    echo "❌ ERROR: Coverage report not found at $REPORT_SRC"
    # List files to help debugging if it fails
    find services/ultrasonic -name "*.xml" | grep jacoco || true
    exit 1
fi

echo "--- Ultrasonic unit tests passed and coverage extracted ---"
