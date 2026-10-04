- **A track queued from the web player sometimes showed no cover in the notification, on the lock
  screen or in the car.** The web player gave the player service a signed `getCoverArt` URL as the
  cover, and the app sent that URL as the `id` of a new `getCoverArt` request. LMS answered
  "Required parameter 'id' is missing". The web player now sends the cover-art id. The app takes
  the id out of a `getCoverArt` URL that an older web bundle still sends, and it does not ask the
  server for any other URL. The URL had the user name, the token and the salt in it, and the app
  kept it with the queued track and in a debug log line. A logged cover-art value now has those
  values replaced by `REDACTED` (bug report 150).

<!-- release notes -->

- Covers of tracks started from the player show again in the notification, on the lock screen and
  in the car.
