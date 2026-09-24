# Every Rematch Miss Moved The Listen To "Now"

# status: fixed — `listened_at` declares its DEFAULT, and migrate_v33 removes the ON UPDATE from the existing tables

# reported problem
Once, in the first 15 minutes after 0.23.0 went out (2026-08-21), the scrobble-rematch worker
logged:

```
scrobble-rematch: pass failed: (1062, "Duplicate entry
'user-2026-08-21 21:02:05-ISAB-The Secret Camo Tower Nobody Kn...' for key 'username'")
```

The value has the shape of `scrobble_unmatched_listens`' UNIQUE key (username, listened_at,
artist_name, track_title). `scrobble_rematch.py` only DELETEs and UPDATEs that table, and both INSERT
sites carry `ON DUPLICATE KEY UPDATE`, so a plain 1062 looked unreachable. It was filed in
`docs/open-work.md` with a guess: that the over-long key had been silently truncated to a prefix.

# Possible reason
The guess was wrong; the key is not truncated. Past InnoDB's index length limit MariaDB builds it as a
`USING HASH` long unique key, which compares the full values.

The real cause is the `listened_at` column itself. `routers/scrobbler.py` created both scrobble tables
with `listened_at TIMESTAMP NOT NULL` as their first TIMESTAMP column and no DEFAULT. Under
`explicit_defaults_for_timestamp=OFF` -- the default on every MariaDB before 10.10, and the tables were
created on 10.6 on 2026-07-04 -- that column silently becomes

```
listened_at timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp()
```

and the attribute stays through any later server upgrade. From then on every UPDATE that changes a
row also rewrites the moment the listen happened:

- `scrobble_rematch.rematch_once` stamps each miss with
  `SET attempts = attempts + 1, last_attempt_at = NOW()` -- so every unmatched listen was moved to the
  time of its latest miss, once per retry window;
- the `ON DUPLICATE KEY UPDATE` in `routers/scrobbler.py` (played_secs top-up) and in
  `scrobble_rematch.record_match` (match method/score) fire it on `scrobble_listens` whenever the new
  values differ;
- the account merge in `routers/users.py` repoints `username`, which moves every listen of the merged
  account to the moment of the merge.

The 1062 is the visible corner of this. Two unmatched listens of the same track by the same user,
stamped as misses within the same second, both become `listened_at = NOW()` and collide on the UNIQUE
key. The failed UPDATE rolls back, the pass aborts, and the next pass (a different second) succeeds --
with the time rewritten. So the error is rare and self-healing, and the damage it signals is silent.

Reproduced on `mariadb:10.6`, the image `scripts/test/db-integration.sh` uses: the new integration test
below fails without the fix with
`IntegrityError: (1062, "Duplicate entry 'user-2026-09-23 14:25:21-ISAB-The Secret Camo Tower' for key 'username'")`.

# solution
- `routers/scrobbler.py` creates both tables with `listened_at TIMESTAMP NOT NULL DEFAULT
  CURRENT_TIMESTAMP` -- an explicit DEFAULT and no ON UPDATE -- and `init_db` removes the attribute
  from an existing table on start-up.
- `migrate_v33_listened_at_no_on_update.sql` does the same on production. It only runs the `MODIFY`
  while `information_schema.columns.EXTRA` still says `on update`: the hash key rules out an in-place
  ALTER, so an unconditional one would copy the table on every deploy.
- No other table has the trap: every other first TIMESTAMP column declares a DEFAULT or NULL, and each
  remaining `ON UPDATE CURRENT_TIMESTAMP` in the schema (`updated_at`, `last_seen`, `last_processed`,
  `last_used_at`) is written out on purpose.
- Tests: `tests/integration/test_scrobble_rematch.py::test_a_miss_leaves_the_moment_of_the_listen_alone`
  (two same-track misses, both `listened_at` unchanged, no 1062), and in `tests/integration/test_schema.py`
  a check that neither `listened_at` carries `on update`, plus one each proving that migrate_v33 and
  `init_db` repair a table put back into production's shape.

This stops further damage; it does not repair values already rewritten. No repair script is part of
this change, because the right source for each row differs.

## Estimating the damage (production, read-only)
First confirm production has the attribute at all:

```sql
SHOW CREATE TABLE scrobble_listens;
SHOW CREATE TABLE scrobble_unmatched_listens;
```

Unmatched listens moved by a miss. Both columns are set by the same `NOW()` in the same statement, so
an exact match is the signature; the second query is the looser bound:

```sql
SELECT COUNT(*) FROM scrobble_unmatched_listens WHERE listened_at = last_attempt_at;
SELECT COUNT(*) FROM scrobble_unmatched_listens WHERE attempts > 0 AND listened_at > created_at;
```

Matched listens rewritten after insert (played_secs top-up, re-match):

```sql
SELECT COUNT(*) FROM scrobble_listens WHERE listened_at > created_at;
```

Listens the rematch linked *after* a miss carry the time of that miss, which is earlier than their
`created_at` and so escapes the query above. Rewritten rows cluster, though -- one rematch pass or one
account merge stamps many rows in the same second, and nobody listens to several tracks in one second:

```sql
SELECT username, listened_at, COUNT(*) AS n
FROM scrobble_listens GROUP BY username, listened_at HAVING n > 2 ORDER BY n DESC;
```

What the real time was: for live rows (`source` in `lms`, `lms-web`, `frontend`, `mobile`, `auto`,
`manual`), `created_at` was written when the scrobble arrived, so it approximates the listen to within
the client's delay. For `source = 'listenbrainz'` rows `created_at` is the import time and says nothing
about the listen; those can only be recovered from ListenBrainz itself.

## Repair (2026-09-24)
For every listen that was played through LMS the real time still exists: LMS's own `listen` table
records `date_time` at the moment it relays the scrobble to muma, and nothing in LMS rewrites it.
`services/music_manager/scrobble_reconcile.py` compares the two per user and track and classifies
every listen as `exact` (within 5 s), `shifted` (a live, rewritten muma row later than an unclaimed
LMS listen of the same track -- this bug's signature), `muma_only` (ListenBrainz, manual, pre-LMS;
left alone) or `lms_only` (a listen muma lost). The rules, and the LMS-to-muma track join by file
path, are in the 2026-09-24 section of
[the technical design](../designs/ratings-scrobbling/technical.md). Admin only:

1. Dry run, writes nothing: `GET /api/scrobble/reconcile/lms` (optionally `?username=user`).
   Check `zones.consistent` is `true` -- if the process and the database session disagree about
   the local zone, every stored time is off by a constant and the apply refuses to run. Read the
   totals and the `sample.shifted` rows: `delta_seconds` should be positive and
   `listened_at` should cluster on a few seconds (a rematch pass, a merge).
2. Apply: `POST /api/scrobble/reconcile/lms` with `{"apply_shifted": true}` first;
   `insert_lms_only` only after the `lms_only` sample has been checked by hand. It runs in the
   background, one transaction per user; the outcome is on `GET /api/scrobble/reconcile/lms/status`
   and as an INFO event "Listens reconciled against LMS". UNIQUE collisions are skipped and counted.
3. Verify: the dry run again shows `shifted: 0`, and `GET /api/listening/timeline` for an affected
   user no longer shows plays piled onto the rematch/merge seconds.

Listens that never went through LMS (`source = 'listenbrainz'`, pre-LMS history) are not touched;
those can only be recovered from ListenBrainz itself.
