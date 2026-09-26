# The song-versions worker grouped 500 tracks an hour and never caught up

# status: fixed

# reported problem
On 2026-09-26, after the 0.76.1 deploy and the regroup of bug report 098, 42,915 tracks were
waiting for a song (`work_id IS NULL`, 41,644 of them with a file). The EPs tree alone had added
4,009 new tracks between 11:50 and 12:23. The worker's hourly tick logged one "recomputed 465
works" per hour. An ungrouped track has no best version, so it is missing from everything that
collapses per song (Release Radar, daily mixes, the shelves).

# Possible reason
`grouping_tick` ran `group_once` once per `SONG_VERSION_INTERVAL` (3600 s), and `group_once`
assigns at most `SONG_VERSION_BATCH` (500) tracks. That is 12,000 a day at best, so the backlog of
about 38,000 that stood before the regroup, and any rescan of the label tree, took days.

# solution
`drain_backlog` runs `group_once` batch after batch within one tick, until no ungrouped track is left,
a batch assigns nothing (tracks that cannot be grouped now must not make it spin), or
`SONG_VERSION_TICK_BUDGET` seconds (default 300) have passed. Every batch still commits on its own.
The tick logs "grouped N tracks in B batches, recomputed W works, R left".
