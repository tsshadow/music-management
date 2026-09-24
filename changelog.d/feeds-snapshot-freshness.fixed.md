- **A daily mix that came out empty stayed empty for the rest of the day.** A listener who opened
  Home before their first listen got `not_enough_data`, and that answer was cached as the day's
  mix. A mix that is not `ok` now lives 15 minutes (`FEEDS_NON_OK_TTL_SECONDS`) and is rebuilt
  after that, on the next read or by the background refresh. A curator's hardness edit and a
  listener's exclusion change now also reach the mixes on the next read, including when a build
  was already running, and the mixes roll over at local midnight (`MUMA_TIMEZONE`, default
  `Europe/Amsterdam`) instead of at 01:00 or 02:00. See
  `docs/bug-reports/049-empty-daily-mix-stays-empty-all-day.md`.
<!-- release notes -->
- Je dagmixen vullen zich nu dezelfde dag nog zodra je iets hebt geluisterd, in plaats van pas de
  volgende dag. Een aangepaste hardheid van een genre is direct zichtbaar, en de mixen wisselen om
  middernacht in plaats van om 01:00 of 02:00.
