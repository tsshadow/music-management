# A Web-Only Release Never Reaches The App

# status: fixed

# reported problem
"I would expect that when 0.84.0 is on prod and I reopen the app, I see the BPM button?" (Teun,
2026-09-29). 0.84.0 added browsing by BPM and the listening-stats filters. Both were live on the web
player, but the app showed neither and offered no update.

# Possible reason
The app has no `server.url` in its Capacitor config: it serves the web bundle that
`prepareWebBundle` (services/muma-mobile/app/build.gradle) copies from `services/frontend/dist` into
the APK. A frontend change therefore only reaches a phone through a new APK with a higher
`versionCode`, which is what the update checker compares.

The 0.84.0 pipeline did build and upload an APK with the new bundle, but with `versionCode 352`, the
same as 7.13.0, so no phone was offered it. `release:version-check` did not object, for two reasons:

- it only looked at `services/muma-mobile/`, not `services/frontend/`;
- it compared the release branch with develop. A release branch is cut from develop, so every change
  merged before the cut is invisible in that diff. The check could only ever catch app changes made on
  the release branch itself, which never happens.

# solution
`release:version-check` now compares `services/muma-mobile/` and `services/frontend/` against
`master` (the last release) and fails when either changed while `versionCode` in build.gradle still
equals master's. `tests/ci/test_release_version_check.py` covers a frontend change and an app change
merged into develop before the cut (both fail without a bump; they failed to fail before the fix) and
the passing case with a bump. The release runbook says that a
frontend change is an app change.

0.84.1 ships the missing app build (7.13.1) with the 0.84.0 web UI.
