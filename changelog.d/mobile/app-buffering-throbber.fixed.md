- **The play button in the app showed no throbber while a track was still loading.** The web player
  got one in 7.18.4, but in the app the playback service never told the web screen it was
  buffering: it only sent an event when playback started or stopped. The service now sends
  `buffering` when Media3 buffers towards playing (`STATE_BUFFERING` with `playWhenReady`), and
  every state snapshot carries the flag. A seek while paused shows no throbber, the same as in the
  browser.

<!-- release notes -->

- **The play button now shows a throbber while a track is still loading.**
