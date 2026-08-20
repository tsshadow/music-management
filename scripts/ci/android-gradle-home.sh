#!/bin/bash
# scripts/ci/android-gradle-home.sh
# Shared helper: picks the Gradle home the MuMa Mobile containers mount, and
# exports GRADLE_HOME_DIR. Source it, do not execute it.
#
#   source "$ROOT_DIR/scripts/ci/android-gradle-home.sh"
#   docker run --rm -v "$GRADLE_HOME_DIR:/gradle_home" ...
#
# Why this is one directory per *environment* and not per concurrent job slot:
#
# It used to be "/tmp/.gradle_muma_${CI_CONCURRENT_ID}", because two MuMa Mobile
# jobs landing on the same runner at the same time would fight over one
# GRADLE_USER_HOME and fail with "Timeout waiting to lock journal cache". That
# worked, but it also meant every runner kept N cold, unrelated Gradle homes:
# the first job to land on a fresh slot re-downloaded ~560 MB of dependencies,
# re-unpacked the Gradle distribution and started from an empty build cache.
# That is exactly the job that took 50-90 minutes and hit the 45m timeout, while
# a warm slot did the same work in ~3 minutes.
#
# The lock contention is now prevented at the source instead: the MuMa Mobile
# jobs in .gitlab-ci.yml share `resource_group: muma-mobile`, so GitLab runs at
# most one of them at a time across the whole project. With no concurrency there
# is nothing to partition, and every CI job gets the fully warm cache.
#
# Local runs still get their own directory: this workstation is itself a
# registered runner (tag "fast"), so a developer running the script by hand
# could otherwise collide with a CI job that resource_group knows nothing about.
if [ -n "$CI_JOB_ID" ]; then
    GRADLE_HOME_DIR="/tmp/.gradle_muma_ci"
else
    GRADLE_HOME_DIR="/tmp/.gradle_muma_local"
fi
export GRADLE_HOME_DIR
mkdir -p "$GRADLE_HOME_DIR"

# A runner that ran the older, root-in-container version of these scripts still
# has a root-owned Gradle home from back then, which the container - now the
# host user - cannot write to. Hand it over once, via a throwaway root
# container, so the switch does not need a manual cleanup on every runner.
if [ -n "$(find "$GRADLE_HOME_DIR" ! -user "$(id -u)" -print -quit 2>/dev/null)" ]; then
    echo "Reclaiming $GRADLE_HOME_DIR for $(id -un)"
    docker run --rm -v "$GRADLE_HOME_DIR:/gradle_home" alpine chown -R "$(id -u):$(id -g)" /gradle_home
fi

# Drop the per-slot Gradle homes this helper replaced. They are ~2 GB each and
# nothing reads them any more; leaving them behind would keep filling the
# runner LXC's disk (see docs/deployment.md on runner disk pressure).
#
# The age guard is not cosmetic. Until this commit is merged everywhere, a
# pipeline built from an older commit - a long-lived release/* branch, say -
# still runs the per-slot version of this script and is still USING one of
# these directories. Deleting a Gradle home from under a running build produces
# exactly the failure that has been misread as a MockK bug before ("Daemon
# registry /gradle_home became unreadable", then 69 NoClassDefFoundError test
# failures), so only reap a directory that nothing has touched for six hours.
if [ -n "$CI_JOB_ID" ]; then
    while IFS= read -r _stale; do
        [ -n "$_stale" ] || continue
        echo "Removing stale per-slot Gradle home $_stale"
        rm -rf "$_stale" 2>/dev/null || \
            docker run --rm -v /tmp:/host_tmp alpine rm -rf "/host_tmp/$(basename "$_stale")"
    done < <(find /tmp -maxdepth 1 -type d -name '.gradle_muma_[0-9]*' -mmin +360 2>/dev/null)
    unset _stale
fi
