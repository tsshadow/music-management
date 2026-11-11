#!/bin/bash
# scripts/test/muma-mobile-emulator-smoke-inner.sh
# Runs INSIDE the Android CI container (see muma-mobile-emulator-smoke.sh for
# the why and the docker invocation). Builds the release APK, boots a headless
# ATD emulator on KVM, installs it, and launches it twice (first start, then a
# cold restart), checking each time that the process survived, that
# CapacitorActivity is resumed, and that the expected text reached the screen.
set -e

. /etc/android-sdk-root
export ANDROID_SDK_ROOT
export ANDROID_HOME="$ANDROID_SDK_ROOT"
export PATH="$ANDROID_SDK_ROOT/platform-tools:$ANDROID_SDK_ROOT/emulator:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$PATH"
# AVDs and adb keys must land somewhere this uid can write. NOT the image's
# /home/ci: the image tag hashes only the Dockerfile, so a runner can inherit
# an image built under a different uid (the workstation did - the local
# build, gitlab-runner's job) and /home/ci then belongs to someone else. The
# wrapper therefore sets HOME=/tmp/emu-home, writable for any uid.
mkdir -p "$HOME"
export ANDROID_AVD_HOME="$HOME/.android/avd"
mkdir -p "$ANDROID_AVD_HOME"

PACKAGE="nl.teunschriks.mumamobile"
APK="app/build/outputs/apk/release/app-release.apk"
SYSTEM_IMAGE="system-images;android-34;aosp_atd;x86_64"
BOOT_TIMEOUT=300
# How long the app gets to crash after launch. The 029 crash fired within a
# second of Application.onCreate; 15s is generous without dragging the job.
GRACE_SECONDS=15
# How long the UI probe keeps re-reading the screen for the expected text. The
# WebView paints a few seconds after the activity resumes on a cold ATD image.
PROBE_TIMEOUT=45

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

# -g grants every runtime permission up front. Without it the first launch
# raises the POST_NOTIFICATIONS dialog on API 34, which becomes the resumed
# activity and the only window uiautomator can see -- the checks below would be
# reading the permission controller, not the app.
adb install -r -g "$APK"
adb logcat -c || true

# One launch through the launcher, the way a phone opens the app: monkey
# resolves the LAUNCHER intent itself, which survives the icon-variant
# activity-aliases (MainAliasGreen/...) that make a hardcoded component name
# brittle - exactly one alias is enabled at a time. LauncherActivity is a
# trampoline, so what must end up resumed is CapacitorActivity.
launch() {
    adb shell monkey -p "$PACKAGE" -c android.intent.category.LAUNCHER 1 >/dev/null
}

dump_crash_context() {
    echo "--- logcat (crash context) ---" >&2
    adb logcat -d | grep -B2 -A30 -E "FATAL EXCEPTION|ANR in $PACKAGE" >&2 || adb logcat -d | tail -100 >&2
}

# The process is alive and no FATAL EXCEPTION or ANR naming the package is in
# the log. logcat is cleared only once, before the first launch, so the second
# (cold) start is also checked against anything the first one left behind.
assert_alive() {
    local label="$1"
    local pid crash anr
    pid="$(adb shell pidof "$PACKAGE" | tr -d '\r' || true)"
    crash="$(adb logcat -d | grep -A2 "FATAL EXCEPTION" | grep -c "$PACKAGE" || true)"
    anr="$(adb logcat -d | grep -c "ANR in $PACKAGE" || true)"
    if [ -z "$pid" ] || [ "$crash" -gt 0 ] || [ "$anr" -gt 0 ]; then
        echo "[$label] Release build did not survive startup (pid='${pid}', fatal-exception hits=${crash}, ANR hits=${anr})." >&2
        dump_crash_context
        exit 1
    fi
    echo "[$label] Process $pid alive after ${GRACE_SECONDS}s, no fatal exceptions or ANRs."
}

# The trampoline handed over and CapacitorActivity reached onResume -- which is
# where the Koin graph is first touched (`lifecycleSupport.onCreate()` resolves
# its `by inject()` there), so a module R8 broke fails here even when the
# process itself survives.
assert_resumed() {
    local label="$1"
    local resumed
    resumed="$(adb shell dumpsys activity activities | tr -d '\r' | grep -E "topResumedActivity|mResumedActivity|ResumedActivity:" | head -1 || true)"
    case "$resumed" in
        *"$PACKAGE/.activity.CapacitorActivity"*)
            echo "[$label] CapacitorActivity is resumed."
            ;;
        *)
            echo "[$label] CapacitorActivity is not the resumed activity: '${resumed}'." >&2
            dump_crash_context
            exit 1
            ;;
    esac
}

# Reads the accessibility tree -- which includes the WebView's DOM -- until
# the given text appears. uiautomator refuses to dump while the screen is still
# animating ("could not get idle state"), hence the loop rather than one shot.
wait_for_text() {
    local label="$1" needle="$2" what="$3"
    local xml=""
    for _ in $(seq 1 "$PROBE_TIMEOUT"); do
        adb shell uiautomator dump /data/local/tmp/ui.xml >/dev/null 2>&1 || true
        xml="$(adb shell cat /data/local/tmp/ui.xml 2>/dev/null || true)"
        if printf '%s' "$xml" | grep -qF -- "$needle"; then
            echo "[$label] Found '$needle' on screen: $what."
            return 0
        fi
        sleep 1
    done
    echo "[$label] '$needle' never appeared on screen within ${PROBE_TIMEOUT}s ($what)." >&2
    echo "--- last accessibility dump (text attributes) ---" >&2
    printf '%s' "$xml" | grep -oE 'text="[^"]+"' | head -40 >&2 || true
    dump_crash_context
    exit 1
}

# What the screen has to show, depending on what the APK carries.
#
# With the Svelte bundle: the first-run server screen (issue #192), since a wiped
# install has no server address yet. A build with its own server prefills the
# field with it. That value only gets there through a JS -> native call
# (`MumaSystem.suggestedServerAddress`, a @PluginMethod the Capacitor bridge
# finds by its method name, after `MumaSystem.serverUrl` answered
# `configured: false`). R8 stripping or renaming the plugin -- see
# minify/proguard-capacitor.pro -- never crashes anything: bootstrapShell catches
# the rejection and the page comes up without the prefill. This is the check
# that notices.
#
# A build with the example default suggests nothing (SMOKE_EXPECTED_SERVER is
# empty); then the screen's example address is the needle, which proves the
# screen mounted but not the prefill round trip.
#
# Without the bundle (no frontend:bundle in the pipeline) the placeholder page is
# all there is, and seeing it only proves the WebView and the bridge came up.
FIRST_RUN_EXAMPLE="https://music.example.net"
if grep -q "The web bundle was not built" app/src/main/assets/public/index.html 2>/dev/null; then
    EXPECT_TEXT="The web bundle was not built"
    EXPECT_WHAT="placeholder page rendered; no Svelte bundle in this APK, so the plugin round trip is NOT checked"
    echo "WARNING: this APK carries the placeholder page, not the Svelte bundle; only the WebView is checked." >&2
elif [ -n "${SMOKE_EXPECTED_SERVER:-}" ]; then
    EXPECT_TEXT="$SMOKE_EXPECTED_SERVER"
    EXPECT_WHAT="first-run screen mounted and MumaSystem.suggestedServerAddress answered across the Capacitor bridge"
else
    EXPECT_TEXT="$FIRST_RUN_EXAMPLE"
    EXPECT_WHAT="first-run screen mounted; this build suggests no server, so the prefill round trip is NOT checked"
    echo "WARNING: this APK was built with the example server; only the first-run screen is checked." >&2
fi

echo "--- First launch ---"
launch
sleep "$GRACE_SECONDS"
assert_alive "first launch"
assert_resumed "first launch"
wait_for_text "first launch" "$EXPECT_TEXT" "$EXPECT_WHAT"
assert_alive "first launch, after the UI probe"

# The second start is a different program from the first: whatever the first
# run persisted (settings, the Room database, Gson models in SharedPreferences)
# is now read back instead of created. That read-back is exactly where the
# 6.21.0 crash lived -- a Gson model R8 had stripped the signature of, fine to
# write and a ClassCastException to read.
echo "--- Cold restart ---"
adb shell am force-stop "$PACKAGE"
sleep 1
launch
sleep "$GRACE_SECONDS"
assert_alive "cold restart"
assert_resumed "cold restart"
wait_for_text "cold restart" "$EXPECT_TEXT" "$EXPECT_WHAT"
assert_alive "cold restart, after the UI probe"

echo "Release build survived two launches; every check passed."
