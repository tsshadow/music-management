- The APK hoster showed no release notes for an app version since the changelog fragments came in: `publish.sh` looked for a `## [7.18.4]` heading in the app's `RELEASE_NOTES.md`, while the release assembler writes `## Global Version 7.18.4 (2026-10-30)`, so no `.txt` notes file went out with the APK. `scripts/release-notes.sh` reads both headings, and `publish.sh` warns when a version has no section.

<!-- release notes -->

- The download page of the app shows the release notes of each version again.
