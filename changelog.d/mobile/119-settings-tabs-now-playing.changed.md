- **The bundled web interface reads settings one tab at a time and Now Playing only when it is
  about to open** (issue #119). The settings tabs are separate files in the APK now: opening
  settings reads 36 kB instead of 81 kB, and a tab still loading shows its own shape in skeleton
  blocks while the next tab is read in the background. The full-screen Now Playing is a separate
  file too, read on idle after the home screen is up and the moment a finger touches the mini
  player; if it is not in yet, the screen appears at once anyway with the cover, title, artist
  and a working play/pause. The file the WebView starts with went from 300 kB to 255 kB.
<!-- release notes -->
- Settings opens faster, and the app's interface starts a little faster again; Now Playing
  still opens instantly.
