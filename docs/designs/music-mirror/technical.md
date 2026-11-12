# Music Mirror: Technical Design

Implements [functional.md](functional.md), with the decisions of 2026-11-12 listed there. The mirror is one nightly `rsync` run from the library
NAS to a second NAS, without `--delete`, followed by a ZFS snapshot on the second NAS. A status
file records each run. The production host reads that file, writes the events and serves
`/health/music-mirror`.

In this document, the **library NAS** holds the live library (the SMB share that production mounts
as `HOST_MUSIC_PATH`, see below). The **mirror NAS** is the 27 TB machine. Host names are
placeholders: `library-nas.example.com`, `mirror-nas.example.com`.

## How the Library Is Reached Today

- Every container that reads or writes music mounts `${HOST_MUSIC_PATH}:/mnt/music`
  (`docker/docker-compose.yml`, `docker-compose.workers.yml`, `docker-compose.tools.yml`). The LMS
  stack mounts it read-only (`docker-compose.core.yml`).
- On production, `HOST_MUSIC_PATH` is a CIFS (SMB) mount of the library NAS. The library NAS
  stores the files on a ZFS dataset, and the client path `/mnt/music/<x>` is the dataset path
  `<dataset mount>/<x>` one for one.
- The database dumps go to `HOST_BACKUP_PATH` (default `/mnt/backups/muma`), which must be on
  another disk than the database (`scripts/backup/install-systemd.sh` checks it). music-manager
  mounts it read-only to answer `/health/backup`.

The mirror does not read through the SMB mount. A walk of about 680,000 files over SMB from the
production host is slow, and it would copy each changed file whole (rsync does not use its delta
transfer between two local paths). The mirror reads the dataset on the library NAS directly, over
SSH.

## Tool Choice

| Tool | Fits | Does not fit |
|---|---|---|
| `rsync` over SSH, no `--delete` (chosen) | Never deletes on the mirror by design. Sends only changed blocks of a changed file. On every NAS. The mirror is plain files: a restore needs no tool. | Walks the whole tree each run (both sides list 680k files). |
| ZFS send/receive | No file walk; incremental streams are cheap. | Replays every delete and every rename into the newest state, which the decision of 2026-11-12 rules out. Needs ZFS on both sides and a common snapshot kept forever. Copies the library's broken POSIX ACLs too. |
| restic or borg | Own version history, deduplication, encryption. | The version history is what the snapshots already give, at a higher cost: a 6 TB repository, an index in memory, and a restore that needs the tool and its key. |
| rclone | Many cloud backends. | No advantage on a LAN, and `sync` deletes by default. |
| Syncthing | Continuous. | Two-way by default and replays deletes. |

## Topology

The job runs on the **mirror NAS** and pulls (decision 1 of the functional design), because no key on the library side or on the production host can then write to the
mirror or remove a snapshot. A compromised production host or library NAS can at worst damage the
library itself, and every snapshot on the mirror stays out of its reach.

Two keys, both made on the mirror NAS for the job's account (`muma-mirror`), installed on the
library NAS by a person:

| Key | `authorized_keys` options on the library NAS | Lets the job |
|---|---|---|
| `muma-mirror-read` | `restrict,command="rrsync -ro <library dataset mount>"` | read the library, nothing else |
| `muma-mirror-status` | `restrict,command="rrsync -wo <status directory>"` | write files into one directory |

`rrsync` is the restricted rsync wrapper that ships with rsync 3.2 and later. The status directory
is the directory that production mounts as `HOST_MIRROR_STATUS_PATH` (below). The default is
`${HOST_BACKUP_PATH}/music-mirror`, next to the database dumps.

## The Job: `tools/music_mirror.py`

One Python file, standard library only, so it runs from a root-owned copy on the mirror NAS
(`/opt/muma-mirror/bin/`) without the rest of the repository. A cron entry on the mirror NAS
starts it nightly at 01:30. It holds a lock file, so two runs never overlap. Configuration is
one `KEY=VALUE` file (`/opt/muma-mirror/env`, mode 0600), parsed without a shell.

Steps of a run:

1. **Preflight.** The SSH connection to the library NAS answers. The source root lists, and every
   folder in `MIRROR_EXPECTED_DIRS` (for example `EPs,Soundcloud,Youtube,artists`) exists in it.
   The mirror dataset is mounted. Pool use is below `MIRROR_POOL_WARN_PERCENT` (default 80), else
   a `WARNING` (the run still goes on).
2. **Dry run.** `rsync` with the flags below plus `--dry-run --itemize-changes --stats`. From its
   output: the number of files in the library, the files to transfer and their bytes.
3. **Change guard.** The run is refused (`result: refused`, nothing copied) when:
   - the library has fewer than 90% of the files of the last good run, or
   - the files to transfer are more than `MIRROR_MAX_CHANGED_PERCENT` (default 5) of the files, or
     their bytes are more than `MIRROR_MAX_CHANGED_GB` (default 200).

   `--allow-large-change` lifts the second limit for one run, for a person after a mass retag.
   `--initial` lifts both for the first full copy.
4. **Copy.**

   ```
   rsync -rltH --inplace --partial --numeric-ids \
         --info=stats2,progress0 --itemize-changes \
         -e "ssh -i <muma-mirror-read key> -o BatchMode=yes" \
         muma-mirror@library-nas.example.com:./ <mirror dataset mount>/
   ```

   - No `--delete` in any form. A test pins that (see Tests).
   - `-rltH`: content, symlinks, times and hard links. No owner, group, mode or ACL: the library
     NAS has POSIX ACLs that lock files in unexpected ways, and copying them would make the mirror
     as hard to read as the library was. A restore sets ownership and mode for the target.
   - `--inplace` writes changed blocks into the existing file instead of a new copy. ZFS then
     keeps only the changed blocks in the snapshot of the night before, not a second copy of the
     whole file. The cost: a run that stops halfway leaves a half-written file in the mirror head.
     The snapshot before it has the good version, and the next run finishes the file.
   - Exit code 0 is `ok`. Exit code 24 (files vanished during the run, for example an import in
     progress) is `ok` with `files_vanished` set. Any other code is `failed`.
5. **Manifest.** The job saves the list of library files at this run (an `rsync -r --list-only`
   call against the library, through the same read key) as `manifest-<stamp>.txt.gz` on the mirror, outside the copied tree. A full
   restore uses it, so that files deleted or moved in the library do not come back (see Restore).
   It keeps the manifests of the last 30 runs.
6. **Snapshot.** After an `ok` run only: `zfs snapshot <mirror dataset>@mirror-<UTC stamp>`.
7. **Retention.** Of the snapshots named `mirror-*`, keep the newest of each of the last 14 days,
   of each of the last 8 ISO weeks and of each of the last 12 months, and remove the rest.
   It never removes the newest snapshot, and never a snapshot without the `mirror-` prefix.
8. **Sample check.** `rsync --checksum --dry-run --files-from=<sample>` against the library, for
   200 files: up to 100 from tonight's transfers, the rest random. rsync reads both sides in full
   and lists every file that differs, which `rrsync -ro` allows. A difference is `ERROR`.
9. **Monthly items**, on the first run of a month:
   - Orphan count: `rsync --dry-run --delete --itemize-changes` lists what a delete would remove.
     Nothing is removed. The job counts those files and sums their size on the mirror side.
   - Full checksum compare over all files (decision 5). `MIRROR_FULL_CHECKSUM_MONTHLY=0` turns it
     off.
10. **Status.** Write `latest.json` through a `.partial` name and a rename (the pattern of
    `tools/db_backup.py`), and push it with the status key. Keep a copy on the mirror.
11. **Push on failure.** On `failed` or `refused` the job posts to the alerts topic of ntfy
    directly, so the phone hears it at night. It does not wait for the production check. The
    ntfy URL and topic are in the env file. A token, when the ntfy server needs one, is referenced
    by name and filled in by the person.

`--prune` is a separate mode that a person starts. It takes a snapshot first, then runs the copy
with `--delete`, and writes the removed count into the status. Without the snapshot it refuses.

### `latest.json`

```json
{
  "run_id": "20261113T003000Z",
  "started_at": "2026-11-13T00:30:00+00:00",
  "finished_at": "2026-11-13T01:12:44+00:00",
  "result": "ok",
  "reason": null,
  "rsync_exit": 0,
  "files_total": 681479,
  "files_transferred": 412,
  "bytes_transferred": 3221225472,
  "files_vanished": 0,
  "snapshot": "mirror-20261113T011244Z",
  "sample": {"checked": 200, "differing": []},
  "orphans": {"files": 1530, "bytes": 21474836480, "measured_at": "2026-11-01T01:40:00+00:00"},
  "full_checksum": {"at": null, "differing": null},
  "pool_used_percent": 31
}
```

`result` is `ok`, `failed` or `refused`. The numbers are an example.

## Production Side

### `/health/music-mirror`

A new endpoint in `services/music_manager/main.py`, next to `/health/backup` and with the same
shape of answer. It reads `${MIRROR_STATUS_PATH}/latest.json`.

| Condition | Status code | `status` |
|---|---|---|
| `MIRROR_STATUS_PATH` not set | 503 | `unconfigured` |
| No `latest.json`, or it does not parse | 503 | `missing` |
| Last run `failed` or `refused` | 503 | `failed` / `refused`, with `reason` |
| Last good run older than `MIRROR_STALE_AFTER_HOURS` (default 36) | 503 | `stale` |
| Sample found differing files | 503 | `differing` |
| Otherwise | 200 | `ok` |

The body adds `finished_at`, `age_hours`, `files_total`, `orphans` and `pool_used_percent`. It is
separate from `/health` for the reason `scripts/backup/README.md` gives: a stale backup is a real
problem, but not an outage of the service. An Uptime Kuma monitor points at it.

`docker/docker-compose.yml` mounts `${HOST_MIRROR_STATUS_PATH}:/mirror-status:ro` into
music-manager and sets `MIRROR_STATUS_PATH=/mirror-status`. Like `HOST_BACKUP_PATH`, the variable
needs a default that renders a valid mount when unset.

### The daily check

`tools/music_mirror_check.py` in the tools image, as a one-shot service `music-mirror-check` in
`docker/docker-compose.backup.yml`. A systemd timer `muma-music-mirror-check.timer` starts it daily
at 09:42 (the database staleness check runs at 09:12). `scripts/backup/install-systemd.sh` installs
it when `HOST_MIRROR_STATUS_PATH` is set.

It reads the same file and applies the same table. Every non-`ok` row gives an `ERROR` event with
source `music-mirror` and a push, through the `alert()` path of `tools/db_backup.py` (push through
`NtfySink` first, then the event row). An `ok` status whose run finished in the last 24 hours
gives one `INFO` event with the counts and no push. This check is the one that writes the event
row, because the mirror NAS has no database access. It is also the check that fires when the job
on the mirror NAS did not run at all.

## Schedule and Duration

| Job | When |
|---|---|
| Mirror run (mirror NAS) | nightly 01:30 |
| Database dump (production) | nightly 03:12 |
| Disk janitor, downloader refresh (production) | 04:00 and 04:17 |
| Mirror check (production) | daily 09:42 |

The first full copy is about 6 TB. At the 510 Mbit/s measured to the library NAS on 2026-09-18
that is about 28 hours; at full gigabit it is about 15 hours. Run it with `--initial` on a
weekend, with the mirror NAS on the same switch as the library NAS. A nightly run is the walk of
both trees plus the changes of one day. Its duration is not measured yet: the first week records
it in `latest.json`, and the staleness limit stays at 36 hours until then.

## Restore

**One file or one folder.** On the mirror NAS, every snapshot is readable at
`<mirror dataset mount>/.zfs/snapshot/mirror-<stamp>/<path>`. A person copies the file to the
library with their own access, not with a mirror key:

```
rsync -rlt --dry-run <snapshot path>/<folder>/ <library dataset mount>/<folder>/
rsync -rlt           <snapshot path>/<folder>/ <library dataset mount>/<folder>/
```

Then `POST /api/scanner/scan/file?path=...` per file, or wait for the scanner's next walk.

**The whole library.**

1. Stop the writers: the downloader and importer workers, and music-manager (its tagger and
   scanner loops write to and read from the library).
2. Pick the manifest of the last good run before the loss (`manifest-<stamp>.txt.gz`).
3. Copy with `--files-from` that manifest, from the matching snapshot, to the new library volume.
   Dry run first. Without the manifest, the files that were only on the mirror (deleted or moved
   in the library) would come back as duplicates.
4. Set ownership and mode the way the SMB share needs them.
5. Start music-manager and run a full scan (`POST /api/scanner/scan/all`). If the restore
   missed folders, the scanner's vanished-file guard (`services/common/vanished_files.py`) stops
   before it deletes more than 10% of the media rows.

**Drill.** After the first full run, restore one release folder to a scratch directory and compare
checksums with the library. Record the date in the issue.

## What a Person Does

1. Bring the mirror NAS online on the LAN, create a pool and a dataset for the mirror (ZFS,
   compression off: audio does not compress), and say where it lives (its address and the
   dataset name) in issue #25.
2. On the mirror NAS: create the `muma-mirror` account, its two SSH keys, and the cron entry. Copy
   `tools/music_mirror.py` to `/opt/muma-mirror/bin/` as root, and fill `/opt/muma-mirror/env`.
3. On the library NAS: check that `rrsync` exists, create the `muma-mirror` account, and install
   the two keys with the forced commands above. Make sure the SSH service starts at boot.
4. On production: set `HOST_MIRROR_STATUS_PATH`, deploy, and install the check timer.
5. Add the Uptime Kuma monitor on `https://<domain>/health/music-mirror`.
6. Start the first run with `--initial` and watch it to the end. Then do the restore drill.

`scripts/music-mirror/install.sh mirror` does step 2 and `install.sh library` step 3. Each prints
every change first and applies them only after the person types `yes`. Step 4 is
`scripts/backup/install-systemd.sh`, as for the database backup. An agent does not run them.

## Code Layout

| File | Runs on | Purpose |
|---|---|---|
| `tools/music_mirror.py` | mirror NAS | the nightly job and `--prune`; standard library only |
| `services/common/music_mirror_status.py` | production | reads `latest.json` and decides the status; shared by the endpoint and the check |
| `tools/music_mirror_check.py` | production, tools image | the daily check that writes the events |
| `scripts/music-mirror/install.sh` | mirror NAS, library NAS | the person's install script: `mirror` or `library` role, dry run first, then confirm by typing `yes` |
| `scripts/backup/systemd/muma-music-mirror-check.{service,timer}` | production | the daily check, installed by `scripts/backup/install-systemd.sh` |

## Data Model

None. No table changes. The status lives in `latest.json`, the history in the events table.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /health/music-mirror` | none, no key | `{status, reason, finished_at, age_hours, files_total, orphans, pool_used_percent}` | 503 for `unconfigured`, `missing`, `failed`, `refused`, `stale`, `differing` (table above) |

No existing endpoint changes.

## Cross-App Impact

None for the apps. music-manager gets one endpoint and one read-only mount. The tools image gets
the check. `docs/self-hosting.md` (Backups) and `scripts/backup/README.md` ("What is not covered")
change in the implementing MR, and `docs/product-goal.md` loses "has no mitigation" once the first
full run and the drill are done.

## Technical Acceptance Criteria

1. A unit test builds the rsync argument list for a normal run and asserts it contains no option
   that starts with `--delete`, `--remove-source-files` or `--max-delete`. Only `--prune` mode
   adds `--delete`, and only after the snapshot call succeeded (a fake `zfs` records the order).
2. The change guard refuses a run at 90% minus one file of the last count, and at the changed
   percent or bytes limit plus one. `--allow-large-change` passes the second and not the first.
3. The retention test, over a generated list of 400 daily snapshot names, keeps exactly the
   14/8/12 set, keeps the newest, and never selects a name without the `mirror-` prefix.
4. Exit code 24 maps to `ok` with `files_vanished`; 23, 12 and 255 map to `failed`.
5. `latest.json` is written through `.partial` and a rename; a killed write leaves the previous
   file in place.
6. `/health/music-mirror` returns each row of the table above, tested with files in a temporary
   directory, as `services/music_manager/tests/test_health.py` does for `/health/backup`.
7. The check emits one `ERROR` with a push for each non-`ok` status, and an `INFO` without a push
   for a recent `ok` run.
8. The restore drill restored one release folder from a snapshot with equal checksums.

## Related Docs

- [scripts/backup/README.md](../../../scripts/backup/README.md): the database backup, whose
  staleness check, status file and alert path this design reuses.
- [docs/product-goal.md](../../product-goal.md): "Risk order", where the gap is named.
- Issue #25: the decision of 2026-11-12.
