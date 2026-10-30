- **A track that would not play stopped the whole queue, and Android Auto showed a play error.**
  The player now drops the track's cached file, if it has one, and loads the track again from the
  server at the same position, while a new download starts. If that fails too, it goes on to the
  next track. It stops, paused and with the error shown, at the end of the queue or after three
  tracks in a row failed, so a server that is down does not walk through the whole queue. A saved
  (pinned) download is never deleted, and offline mode deletes nothing. This is in the playback
  service, so it is the same in the app, the notification and the car. Each step is a line in the
  diagnostics report (`action player.error`, `action player.recover.*`).

<!-- release notes -->

- **A track that would not play stopped the music, also in Android Auto.** The app now tries the
  track once more from the server, and then goes on to the next track.
