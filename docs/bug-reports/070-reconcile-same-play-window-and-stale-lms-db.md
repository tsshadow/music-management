# The LMS listen reconcile could insert a play twice, split one user in two, and every LMS sync kept meeting a stale lms.db

# status: fixed

# reported problem

The first production dry run of the LMS listen reconcile (`GET /api/scrobble/reconcile/lms`,
release 0.73.2, 2026-09-25) returned: exact 2684, shifted 0, muma_only 21951, lms_only 1453,
lms_only_insertable 254, lms_unmapped 87. Three things were wrong.

1. **The insert guard was too loose.** LMS listen 37787 (track 9374019) was recorded at
   06:08:56 UTC. muma's `scrobble_listens` has the same play for the same user and track at
   06:09:51, source `mobile`. That listen was correctly not insertable, but only because the
   same track still had an unpaired muma listen. If the app had matched the play to a different
   track, or not matched it at all, the reconcile would have called it insertable, and
   `insert_lms_only` would have counted it twice.
2. **One person counted as two users.** Since 05:05 UTC that day a login-case bug (bug report
   074) put the same account in both LMS and muma as `user` and as `Teun`. The dry run showed
   `Teun` (26/0/5/5/0) apart from `user` (2638/0/21607/1447/254), and plays under different
   spellings could never pair.
3. **A stale second database everywhere.** `/app/data/alpha/lms.db` has LMS schema 114, no `user`
   table and no server behind it. It was last written on 2026-09-24. Bug report 069 made the
   reconcile skip it. The song-version sync skipped it too, but every one to two minutes it
   logged `server-alpha: no version columns yet, skipping the song-version sync` at INFO, and
   the retry loop treated the file as a server that was still migrating.

# Possible reason

1. `classify()` used one window, `EXACT_WINDOW_SECONDS = 5`, for two different questions. For
   pairing a muma listen with its own track, 5 s is right: a relayed scrobble carries LMS's own
   timestamp. The same-play guard asks something else: is there any listen of this user that
   could be this play? LMS records a listen when playback *starts*. The app scrobbles to muma
   about a minute later, using its own clock. A 5-second window cannot see that listen.
2. Every username comparison was case-sensitive: the grouping in `classify()`, the dedupe in
   `load_lms_listens()`, the per-user totals and the LMS username filter.
3. `lms_db_targets()` returned every `/app/data/*/lms.db` without looking inside. Each consumer
   ran into the stale file separately: the reconcile, the user and playlist sync, artist images,
   song versions and release dates.

# solution

1. The same-play guard now uses its own window, `SAME_PLAY_WINDOW_SECONDS = 600`. It is one
   symmetric window, applied to both `listened_at` and `created_at`. 600 s covers the gap between
   playback start and the scrobble (55 s observed) plus clock skew between phone and server,
   with a wide margin. The price is on purpose: a lost scrobble within ten minutes of any other
   listen of that user is still reported, but never inserted. A missed insert loses nothing that
   was not already lost; a double count corrupts every statistic built on it. Exact and shifted
   pairing still use `EXACT_WINDOW_SECONDS`. The dry run's `lms_only_insertable` is computed
   under the new rule.
2. Usernames are compared with `str.casefold()` for grouping, pairing and the guard.
   `_analyse()` rewrites every name to muma's `users.username` before classifying; when two
   spellings exist, the oldest account wins. So `user`/`Teun` is one user in the totals, and an
   insert uses muma's spelling, never LMS's. An LMS user that muma does not know under any
   spelling is never insertable. The LMS username filter uses `COLLATE NOCASE`.
3. The new module `services/music_manager/lms_schema.py` owns the schema check
   (`LMS_REQUIRED_TABLES`: `listen`, `user`, `track`). `lms_db_targets()` passes its list through
   `usable_lms_targets()`, which opens each file read-only. A file that answers but lacks a core
   table is dropped, with one WARNING per process per path. The warning is remembered; the
   verdict is not, so a file that later gets the schema comes back. A file that cannot be read at
   all (missing or locked) is kept, because that is transient and every consumer already handles
   it best-effort. `open_servers()` no longer checks the schema itself.

Tests: `services/music_manager/tests/test_scrobble_reconcile.py` checks that a +55 s listen of
another track blocks the insert, that a listen 20 minutes away does not, the window boundary, that
exact and shifted pairing are unchanged, that `user`/`Teun` pair as exact, and that an insert uses
muma's spelling. `services/music_manager/tests/test_lms_schema.py` checks that a stale file is
dropped from `lms_db_targets()` and warned about only once across two calls.

Deleting `alpha/lms.db` from production is still a separate decision. Nothing depends on it any
more.
