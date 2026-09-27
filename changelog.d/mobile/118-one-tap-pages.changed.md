- **The bundled web interface reads another 70 kB less before it appears** (issue #118). The
  artist, album, feed, preset and playlist pages and the list filter bar are separate files in the
  APK now, read on idle after the home screen is up or the moment a link is pressed; the artist and
  album heading still appears at once from what the tapped link knew. The file the WebView starts
  with went from 370 kB to 300 kB, and everything read before the app appears from 580 kB to
  511 kB. The translation file in use is announced to the WebView up front as well.
<!-- release notes -->
- The app's interface starts a little faster again; artist and album pages still open instantly.
