- **A smart playlist deleted or given away in the player stayed in music-manager.** The hourly
  sync from LMS only added playlists and changed their name and rules. It now deletes the copy of
  a playlist that LMS no longer has and moves a playlist to its new owner, all in one transaction.
  A failed sync is a `WARNING` event "Playlist sync failed for <server>" instead of a line in the
  container output (issue #223).
<!-- release notes -->
- **Playlists deleted or given away in the player now follow in music-manager within an hour.**
