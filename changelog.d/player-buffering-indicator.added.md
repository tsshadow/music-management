- **The web player shows a throbber on the play button while a track buffers.** Before, the button
  showed the pause icon as soon as play was pressed, also while the browser still waited for the
  first data or for a seek into a part not loaded yet. The silence looked like a fault. The player
  bar, the mini player and Now Playing now show the spinning ring until the audio plays, and the
  button still pauses. The engine follows the element's `waiting` event, and `stalled` only below
  the ready state that lets playback go on. In the app the button keeps its icon: the native
  engine does not report buffering yet.

<!-- release notes -->

- **The web player shows a throbber on the play button while a track buffers**, so a slow start
  no longer looks like a fault. The app is not changed.
