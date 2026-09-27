- **The bundled web interface starts with less than half the JavaScript it used to** (issue #114).
  The bundle in the APK was one 1.29 MB file that the WebView parsed in full -- every Beheer tab,
  the settings pages, the statistics pages and all four translation files -- before the home
  screen could paint. Pages off the first screen are now separate files in the APK, read when
  opened; the file the WebView starts with went from 1,289 kB to 370 kB, and everything read
  before the app appears (that file, what it imports and the one translation in use) is 580 kB.
  The boot screen stays up until the page the app opens on has loaded, so the app still appears
  whole; a page opened later shows skeleton rows for the moment it takes to read its file. The
  files are local to the APK, so nothing here depends on the network.
<!-- release notes -->
- The app's interface starts faster: it reads less than half the code at start, and loads pages
  like settings and statistics when you open them.
