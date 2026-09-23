- **Every scrobble-rematch miss moved the listen to "now".** Both scrobble tables were created on
  MariaDB 10.6 with `listened_at TIMESTAMP NOT NULL` and no DEFAULT, which that server turns into
  `ON UPDATE CURRENT_TIMESTAMP`. Each miss stamp, played_secs top-up, re-match and account merge
  therefore rewrote when the listen happened; two misses of the same track in one second collided on
  the unique key, which is the `1062 Duplicate entry ... for key 'username'` seen after 0.23.0 — not
  the key truncation `docs/open-work.md` suspected. `listened_at` now declares its DEFAULT, and
  `migrate_v33_listened_at_no_on_update.sql` removes the attribute from the existing tables. Values
  already rewritten are not repaired; bug report 039 says how to count them.
- **Two join columns were never indexed.** `library_tracks.primary_artist_id` (every rematch tier,
  the artist statistics and the feeds join on it) and `scrobble_listens.track_id` — which
  `migrate_v20` claimed already had an index. `migrate_v34` adds `idx_tracks_primary_artist` and
  `idx_listens_track_user (track_id, username)`.
<!-- release notes -->
- **Luistermomenten schoven naar "nu" bij elke mislukte herkoppelpoging.** Dat gebeurt niet meer;
  wat al verschoven is, wordt nog niet hersteld.
- **Twee ontbrekende database-indexen toegevoegd**, voor snellere statistieken en herkoppeling.
