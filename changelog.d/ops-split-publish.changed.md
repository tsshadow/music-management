- **A release no longer deploys from this repository; the tag is what an installation deploys.**
  `muma:deploy`, `muma:verify` and `release:verify-deployed` are gone, and so is
  `scripts/ci/verify-prod-version.sh`. `mobile:build-release` publishes the signed APK, its release
  notes and its mapping to the package registry (`muma-mobile/<versionName>`) and no longer uploads
  to the app download service. On `master`, the new `release:publish` checks that the release
  branch pipeline built the images and the APK for the merged commit, and `release:tag` waits for
  it. A release whose build was skipped or cancelled is no longer tagged. The operations repository
  deploys from the tag and uploads the APK afterwards (#200,
  [docs/designs/ops-split/](docs/designs/ops-split/functional.md)).
<!-- release notes -->
- A release is deployed from its tag by the operations repository. The release pipeline here
  builds and publishes the images and the APK, and tags only when both exist (#200).
