- **A bulk artist-image run went blind after an hour.** The Spotify token was fetched once and
  kept forever; client-credentials tokens expire after 3600 s, so every lookup after the first
  hour answered 401 and the rest of a ~45.000-artist run was deferred. The token is now renewed
  before it expires, and a 401 renews it and retries once. (Bug report 043.)
- **Clearing a portrait in the manager was undone at the next restart.** The clear set
  `image_status = 'none'`, which the start-up run treats as "never asked". It now sets `cleared`,
  which the bulk run and a plain `/fetch-image` skip; "search automatically" in the manager sends
  `force=true` and still reaches it.
- **One failed download marked an artist `failed` for 30 days.** A provider had found the artist;
  the CDN or the disk had not cooperated. A failed download or save now records nothing and the
  artist is asked again next run, and the downloader pauses 1 s, then 2 s, between attempts.
- **Last.fm's placeholder was taken for a portrait.** `artist.getinfo` returns the same grey star
  for every artist, and with an MBID it scored as a known match. It is skipped now.
- **`manifest.json` in the artist-image folder is no longer maintained.** It was rewritten in full
  after every artist and nothing read it. Existing files are left on disk.
- **The config store's file beat every deploy.** `data/config.json` held a snapshot of every value,
  secrets from the environment included, and was loaded after the environment. Now only values
  changed through the config page are written (mode 0600), a value set back to its environment value
  is removed from the file, and an existing file is cleaned up at start-up -- a secret the
  environment also sets is left to the environment. The `db_*` fields, which nothing read through
  the store, are shown read-only. The radio scheduler now resolves the LMS Subsonic key the way the
  scan trigger does.
- **LMS errors no longer leak the Subsonic key or flood the alerts.** The key travels in the query
  string, and requests' error text carries the full URL; the radio logged it at WARNING -- an event
  and an ntfy alert -- per channel every five seconds while LMS was down. Query strings are now
  redacted, and the radio warns once per channel per outage.

<!-- release notes -->

- **Artist portraits:** a long portrait run no longer stops finding anything after an hour, a
  portrait you remove stays removed, and a temporary download error no longer hides an artist for
  a month.
- **Settings:** values from the environment are no longer frozen into the settings file, secrets are
  no longer echoed back after saving, and the database settings are shown read-only.
- **Radio:** a down LMS no longer sends an alert every five seconds.
