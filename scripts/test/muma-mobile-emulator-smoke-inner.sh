#!/bin/bash
# scripts/test/muma-mobile-emulator-smoke-inner.sh
# Runs INSIDE the Android CI container (see muma-mobile-emulator-smoke.sh for
# the why and the docker invocation). Builds the release APK, boots a headless
# ATD emulator on KVM, installs, launches, and checks the process survived.
set -e

. /etc/android-sdk-root
export ANDROID_SDK_ROOT
export ANDROID_HOME="$ANDROID_SDK_ROOT"
export PATH="$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/emulator:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$PATH"
# AVDs and adb keys must land somewhere this (non-root) uid can write.
export ANDROID_AVD_HOME="$HOME/.android/avd"
mkdir -p "$ANDROID_AVD_HOME"

PACKAGE="nl.teunschriks.mumamobile"
APK="app/build/outputs/apk/release/app-release.apk"
SYSTEM_IMAGE="system-images;android-34;aosp_atd;x86_64"
BOOT_TIMEOUT=300
# How long the app gets to crash after launch. The 029 crash fired within a
# second of Application.onCreate; 15s is generous without dragging the job.
GRACE_SECONDS=15

echo "--- Building the release APK (R8-minified, throwaway keystore) ---"
# build.sh generates keystore.jks when no SIGNING_STORE_FILE is set; the
# throwaway signature is irrelevant here - R8 ran, which is what this tests.
./scripts/build.sh release
test -f "$APK"

echo "--- Creating the ATD AVD ---"
echo no | avdmanager create avd --name ci-smoke --package "$SYSTEM_IMAGE" --force >/dev/null
# The base image keeps cmdline-tools outside the SDK root, so avdmanager
# resolves the SDK root as their parent directory and records image.sysdir
# relative to *that*; the emulator then prepends the real ANDROID_SDK_ROOT and
# looks for .../android-sdk-linux/android-sdk-linux/... ("Broken AVD system
# path"). An absolute path sidesteps the whole disagreement.
sed -i "s|^image.sysdir.1 *=.*|image.sysdir.1=$ANDROID_SDK_ROOT/system-images/android-34/aosp_atd/x86_64/|" \
    "$ANDROID_AVD_HOME/ci-smoke.avd/config.ini"

cleanup() {
    adb emu kill >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "--- Booting the emulator (headless, KVM) ---"
EMULATOR_LOG="$HOME/emulator.log"
emulator -avd ci-smoke \
    -no-window -no-audio -no-boot-anim -no-snapshot -wipe-data \
    -gpu swiftshader_indirect \
    -accel on >"$EMULATOR_LOG" 2>&1 &
EMULATOR_PID=$!

# Not `adb wait-for-device`: that blocks forever when the emulator process
# dies before registering, which is exactly the failure worth reporting.
for i in $(seq 1 "$BOOT_TIMEOUT"); do
    if ! kill -0 "$EMULATOR_PID" 2>/dev/null; then
        echo "Emulator process died during boot; its log:" >&2
        tail -50 "$EMULATOR_LOG" >&2
        exit 1
    fi
    if [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; then
        echo "Booted after ${i}s."
        break
    fi
    if [ "$i" -eq "$BOOT_TIMEOUT" ]; then
        echo "Emulator did not boot within ${BOOT_TIMEOUT}s; its log:" >&2
        tail -50 "$EMULATOR_LOG" >&2
        exit 1
    fi
    sleep 1
done

echo "--- Installing and launching $PACKAGE ---"
adb install -r "$APK"
adb logcat -c || true
# monkey resolves the LAUNCHER intent itself, which survives the icon-variant
# activity-aliases (MainAliasGreen/...) that make a hardcoded component name
# brittle - exactly one alias is enabled at a time.
adb shell monkey -p "$PACKAGE" -c android.intent.category.LAUNCHER 1 >/dev/null

sleep "$GRACE_SECONDS"

PID="$(adb shell pidof "$PACKAGE" | tr -d '\r' || true)"
CRASH="$(adb logcat -d | grep -A2 "FATAL EXCEPTION" | grep -c "$PACKAGE" || true)"

if [ -z "$PID" ] || [ "$CRASH" -gt 0 ]; then
    echo "Release build did not survive startup (pid='${PID}', fatal-exception hits=${CRASH})." >&2
    echo "--- logcat (crash context) ---" >&2
    adb logcat -d | grep -B2 -A30 "FATAL EXCEPTION" >&2 || adb logcat -d | tail -100 >&2
    exit 1
fi

echo "Process $PID alive after ${GRACE_SECONDS}s, no fatal exceptions."
