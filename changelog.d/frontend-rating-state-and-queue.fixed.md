- **A rating set in one place of the web player now shows everywhere at once.** Bug report 078:
  the track list, the player bar, Now Playing, the details sheet and car mode each kept their own
  copy of "the rating I last set", so rating a track in one left the others on the old stars until
  a reload. All of them now read and write one shared store (`services/frontend/src/lib/ratings.js`):
  the new value shows at once, is rolled back with the usual "could not save your rating" message
  when LMS refuses it, and a late failure can no longer undo a newer tap. 1-5 stars as before, and
  clearing is its own call (`rating=0`, which LMS relays as `rating_removed`).
- **Tapping a radio channel twice, or a second channel while the first was still tuning in, no
  longer starts two streams.** Every start takes a ticket and only the newest one may touch the
  player once its await returns; a superseded radio controller can no longer load its stream over
  the newer one, or tear down the newer channel when its own start fails late.
- **Saving a long queue as a playlist, and pushing a long jam queue, no longer fail with 414 URI Too
  Long.** `createPlaylist` and `savePlayQueue` now carry their track ids in a form-encoded POST body
  (OpenSubsonic `formPost`, which LMS already accepts) instead of the query string; saving a
  playlist also reports a refusal inside a Subsonic 200 instead of calling it saved.
- **The player no longer writes its state to localStorage four times a second.** `playerState` is
  written at most every five seconds while playing, plus straight away on pause, when the page is
  hidden and on `pagehide`, so the last position still survives a reload.

<!-- release notes -->

- **Web player: a rating now shows in every view at once, radio cannot start twice from a double
  tap, long queues save again (no more "URI too long"), and the player writes less to storage.**
