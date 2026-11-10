- **An artist page and the label edit page now list the channels linked to them.** The artist page
  shows the **Kanalen** section of the label page for the SoundCloud, YouTube and Telegram channels
  a curator linked to that artist (`GET /api/channel-links/by-artist?name=`, looked up by name
  because the page's route carries the player's artist id). The label edit page (Beheer > Curatie)
  shows the label's channels with an unlink button on each, and a tap on a channel opens its tracks
  there too (issue #126).

<!-- release notes -->

- Artist pages show the channels linked to the artist, and the label edit page lets a curator unlink
  a channel.
