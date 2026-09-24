- **Radio kept polling the server after the player was gone.** Nothing cancelled the playback
  service's background work, so once the service was destroyed the radio sync loop went on calling
  the server every 2 to 10 seconds and calling into a released player. The service now shuts down
  once, through a single path, and cancels everything it started (bug report 048).
- **Swiping the app away stopped the music.** Only a paused or empty player stops the service now.
- **A Bluetooth play button could go unanswered.** With no saved queue, or one that could not be
  read, the app never answered the system's request to resume. It now always answers.
- **Radio channels could fail to start on the phone.** Their stream address was taken apart as if it
  were a library track and the load failed. A finished stream address now goes out unchanged.
- **The saved queue and position could be one change behind.** Updates that arrived while the
  previous one was being written were thrown away; the newest one is now written right after.
- **Every settings save, tile change and diagnostics upload logged in with the password first.**
  The stored MuMa API key was never read, so each of those calls also counted towards the login rate
  limit. The stored key is used now, and the app logs in again only if the server refuses it.
- **A failing background call in the app could crash it, and the web UI kept waiting.** Such a call
  now reports an error to the web UI instead, and background work stops when the app is closed.
- **Downloads ran as a media-playback service.** They are declared as data transfer now, which is
  what Android 14 and later expect. A download that Android refuses to start in the background no
  longer blocks every later download until the app restarts.
- **Other apps could control playback.** The receiver for the widget's play, pause and skip buttons
  accepted commands from any installed app. It now only accepts them from MuMa itself.
- **The equalizer was not released when the player changed**, and could be adjusted on an effect
  whose player was already gone.

<!-- release notes -->

- **Playback service fixes.** Music keeps playing when the app is swiped away, radio no longer runs
  on after the player stops and starts reliably on the phone, a Bluetooth play button is always
  answered, the saved queue stays current, and the app no longer logs in again for every settings
  save.
