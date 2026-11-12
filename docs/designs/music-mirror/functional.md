# Music Mirror: Functional Design

## Overview

The music files are the one part of an installation that has no copy. The library is over 6 TB
and about 680,000 files, on one NAS. The database has a nightly verified dump and a weekly restore
drill (`scripts/backup/README.md`). The files have nothing, and `docs/product-goal.md` names that
as the largest risk of the project (issue #25).

This design adds a mirror: a full copy of the library on a second NAS of 27 TB, refreshed every
night. The mirror does two things that a plain copy does not:

- It never deletes a file because the file is gone from the library. A file that the tagger, the
  importer or a person removes, renames or moves stays on the mirror at its old path.
- The second NAS takes a filesystem snapshot after each good run. A file that a run overwrote, for
  example with a damaged or encrypted version, is still in an older snapshot.

Version history per file is not needed. A music collection grows and rarely changes, so a
snapshot costs only the blocks that changed since the snapshot before.

The run reports to the event log and to the alerts topic on the phone, like the database backup
does. A monitor outside the host sees when the mirror is too old.

## User Stories

- As the owner, I want a second copy of every music file on another machine, so that one dead
  NAS, one bad disk pool or one wrong command does not lose the collection.
- As the owner, I want a file that was deleted or overwritten in the library to stay recoverable
  for months, so that a fault I notice late can still be undone.
- As the owner, I want a phone alert when the mirror fails or stops running, so that a broken
  backup does not stay broken for weeks, as the database backup did between 23 July and
  31 August 2026.
- As the owner, I want to get one file or one folder back without a full restore, so that a
  small mistake has a small fix.
- As the owner, I want the mirror to stop and ask when a run would change a large part of the
  library, so that a fault on the library side does not spread to the copy.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| A normal night | The run copies the new and the changed files, the second NAS takes a snapshot, and the event log gets one `INFO` line with the counts (files copied, bytes, duration). No push. |
| A file was deleted from the library | The mirror keeps it. The monthly report counts it as "only on the mirror". |
| A release folder was moved by the importer | The mirror holds the new path and keeps the old one. Both are counted, the old one as "only on the mirror". |
| The tagger rewrote the tags of 300 files | The run copies those 300 files. The previous versions stay in the snapshot of the night before. |
| A run would change more files than the limit (default 5% of the files or 200 GB) | The run stops before it copies anything, logs an `ERROR` with the numbers and pushes an alert. The mirror is untouched. A person checks the library and starts the run again with an override. |
| The library mount is missing or empty | The run stops before it copies anything, with an `ERROR` and an alert. |
| The second NAS is off or unreachable | The run fails with an `ERROR` and an alert. The staleness check alerts too once the last good run is older than the limit. |
| No run has finished for 36 hours | The daily check pushes an alert, and `/health/music-mirror` answers 503, so the Uptime Kuma monitor goes red. |
| A sample file differs between library and mirror after a run | The run logs an `ERROR` that names the file, and pushes an alert. |
| The mirror holds a lot of data that is only on the mirror | The monthly report says how many files and bytes. A person decides whether to prune. A prune runs only after a fresh snapshot, so the pruned files stay in the snapshots until those expire. |
| A person wants one file back | They copy it from the newest snapshot that has it, or from the mirror head. Nothing else changes. |
| The library NAS is lost | A person copies the whole mirror back to a new library volume, then runs a full scan. The procedure is in the technical design. |

## Acceptance Criteria

1. After the first full run, every file in the library exists on the mirror with the same size
   and the same content, checked by a full checksum comparison once.
2. A file deleted from the library is still on the mirror after the next ten runs.
3. A file overwritten in the library can be read in its old form from the snapshot of the night
   before the change.
4. A night without a successful run leaves an `ERROR` event and an alert on the phone within
   36 hours, also when the timer itself did not run.
5. `/health/music-mirror` answers 200 while the last good run is younger than the limit, and 503
   when it is older, when the status is missing, or when the last run failed.
6. A run that would change more than the limit copies nothing and says why.
7. A run never removes a file from the mirror. Only a prune that a person starts does, and only
   after a snapshot.
8. The restore of one folder from a snapshot is written down and was done once as a drill.

## Open Questions / Not Yet Decided

1. Where the run starts: on the second NAS, pulling from the library NAS (recommended, because
   nothing on the library side can then write to or delete from the mirror), on the library NAS,
   pushing, or on the production host over the library's SMB mount.
2. Is the second NAS on all the time, or only during a window (for example woken at 01:00 and shut
   down after the run)? This sets the staleness limit: 36 hours for nightly runs, 8 days for weekly.
3. Snapshot retention: 14 daily, 8 weekly and 12 monthly snapshots (recommended), or longer for
   monthlies.
4. Does the mirror go offsite later? A second NAS in the same house protects against a dead NAS
   and a wrong command, not against fire or theft.
5. The size of the full checksum comparison: once a month over all files (about a day of disk
   reads on both sides), or only the nightly sample of 200 files.
