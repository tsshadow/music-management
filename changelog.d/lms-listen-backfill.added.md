- **MuMa now inserts, by itself, the listens LMS recorded but never passed on.** LMS forwards each
  listen once, retries twice in a row and then drops it, so every MuMa restart (every deploy)
  lost the listens made during it. On 2026-09-25 three of four morning listens went missing this
  way, and the reconcile counts 1,453 such listens overall. A new `lms-listen-backfill` loop reads
  the last 48 hours of LMS's own listen history every 15 minutes. It inserts each lost listen with
  source `lms-backfill` and LMS's start time. It uses the reconcile's rules: nothing within ten
  minutes of another listen by the same user, nothing from the last half hour, and it never moves
  an existing listen. Switch, interval and window are on Beheer > Config under "Scrobbling". The
  thread appears in `/health`. Older history remains a one-off `POST /api/scrobble/reconcile/lms`
  with `insert_lms_only` (bug report 075).
<!-- release notes -->
- Listens made while MuMa was restarting are no longer lost: MuMa now copies them over from LMS's
  own history within about half an hour.
