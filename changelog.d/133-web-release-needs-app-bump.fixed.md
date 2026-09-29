- **A release that changes the web UI now always ships a new app build.** The app serves the web
  interface baked into its APK, but the release check only asked for an app version bump when
  `services/muma-mobile` changed, and compared against develop, where every change merged before the
  cut is invisible. So 0.84.0's BPM browsing and statistics filters reached the web player but no
  phone. The check now compares both the app and the frontend against the last release (bug report
  133).
