- **MuMa Wrapped has a backend: `/api/wrapped`.** `GET /api/wrapped/user` gives your own year (or
  any range up to three years) as about 38 cards: listening time, top tracks, artists, genres,
  labels and channels, festivals and shows, tempo, the listening clock, streaks, sessions, release
  years, ratings and the word of the year. `GET /api/wrapped/library` gives the same for every
  account together, plus the collection (releases, downloads, growth, the shelf) and the system,
  without one username in it. Each card says what it is based on, and a card without enough data
  is left out with its reason. A tab is computed once and stored, so the second open is one
  database read; `POST /api/wrapped/refresh` (admin) recomputes a period.
- **Every new track now records when it arrived and how** (`library_tracks.arrived_at`,
  `arrived_source`: SoundCloud, YouTube, Telegram, label or import). A retag keeps the first
  arrival. `tools/backfill_arrival_dates.py` fills older tracks from the download archives and the
  ingestion records, and leaves a track unknown when the only date is a later redownload.
<!-- release notes -->
- **MuMa Wrapped: the server side.** Your year in music, and the whole library's, as a set of cards.
  The page itself follows in the web player.
