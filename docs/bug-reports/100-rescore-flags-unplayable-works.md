# The first rescore flagged 77k works without a file as changed versions

# status: fixed

# reported problem
After the 0.76.0 deploy on 2026-09-26, the song-versions worker logged
"ranking v2-lossless applied: 330803 works, 351326 tracks rescored, 79267 canonicals changed".
Only about 20,000 works hold more than one track, so 79,267 real changes are impossible. The
Versies page's "changed" filter, which is meant for a curator to review what the new ranking
replaced, would have listed all of them.

# Possible reason
The new ranking lets only a track with a file win (`best_track`, mirroring `_BEST_TRACK`).
76,937 works hold only tracks without a `library_media_files` row (81,888 such tracks on
production), whose canonical used to point at one of them. The rescore set those canonicals to
NULL, which is correct, but recorded the NULL as a replaced version: `previous_canonical_track_id`
and `canonical_changed_at` were set and the change was counted. Measured on production: of the
works flagged by the rescore, 4,420 have more than one track; 74,847 have a single track without a
file.

# solution
`rescore_batch` treats a canonical that becomes NULL like one that appears from NULL: it writes
the new value without a review flag and does not count it. `migrate_v45_rescore_unflag_unplayable.sql`
clears the flag on works that have no canonical, so the page shows the ~2,300 genuine changes
(re-runnable). The rescore itself is not rerun: its canonicals were already right.

Why 81,888 tracks have no file row is a separate question (GitLab issue).
