# Watchtower recreated the pre-deploy db-backup run, and two dumps wrote one file

# status: fixed

# reported problem

On 2026-09-27 the `DEPLOY_DB=1` deploy of release/0.79.4 (pipeline 3952, job 39742 `muma:deploy`),
which was meant to roll out the approved MariaDB 13 upgrade (#14), stopped at
"[2/6] Pre-deploy database backup":

```
05:04:21 Running the db-backup service from /opt/muma-backup (tools/db_backup.py)
05:04:22 Creating music-management_db-backup_run ... done
05:05:03 No such container: c731a7400d1727daf7d472ba6b26469d82565312c739e5ad06140f132111e6da
05:05:03 WARNING: the db-backup service failed; falling back to mariadb-dump through docker exec.
05:06:40 gzip: /mnt/user/muma-backups/muma_db_pre-deploy_20260927_050503.sql.gz.partial: invalid compressed data--format violated
05:06:40 Error: the dump does not decompress; refusing to deploy without a backup.
```

Refusing was correct; the backup itself broke. On the host, a second run container,
`music-management_db-backup_run_b122d69ad4f5`, had started at 05:05:03.566 and exited 1 at
05:07:37 with `FileNotFoundError: ... muma_db_pre-deploy_20260927_050503.sql.gz.partial` -- the same
file name as the fallback's. The first run's partial file stopped growing at 05:05:03 (117 MB). The
database did not restart and nothing was OOM-killed. The pre-deploy dump of the ordinary 0.79.4
deploy at 02:48 and the nightly backup had both worked.

# Possible reason

Watchtower. Its log on the host (times in UTC+2):

```
07:04:37 Found new muma/muma-tools:latest image (2eed1d3d55b8)
07:04:42 Stopping /muma-soundcloud-fetcher (decda39644f7) with SIGTERM
07:04:52 Creating /muma-soundcloud-fetcher
07:04:52 Stopping /music-management_db-backup_run_b122d69ad4f5 (c731a7400d17) with SIGTERM
07:05:03 Creating /music-management_db-backup_run_b122d69ad4f5
07:05:03 Session done  Scanned=18 Updated=2
```

1. **Why the first run container disappeared.** Watchtower on the host is not scoped
   (`WATCHTOWER_LABEL_ENABLE=false`, no container carries an enable label; see #68), runs a session
   every hour at about xx:04, and on that session found a new `muma-tools:latest`. It updates every
   *running* container on an image that changed -- and the deploy's one-off `db-backup` run, started
   17 s before the session, was one. It sent SIGTERM, waited its 10 s, removed the container and
   created a fresh one. Not the stall watchdog (that only exists in the fallback, which had not
   started yet), not compose, and not `DEPLOY_DB=1`.
2. **Why a second run container started.** Watchtower recreates a container from its own
   configuration: same name, same image (now the new one), same environment -- including
   `BACKUP_LABEL=pre-deploy` -- and starts it. That started a second `tools/db_backup.py`. compose
   v1, attached to the container id that no longer existed, printed `No such container` and exited
   non-zero, so the deploy took that as a failed service run and started its fallback.
3. **Why fallback and second run shared a file name.** Both name the file after the UTC time to the
   second (`muma_db_pre-deploy_%Y%m%d_%H%M%S.sql.gz` plus `.partial`), and both started at 05:05:03.
   Two gzip streams interleaved in one file. The fallback's `gzip -t` refused it and its `EXIT` trap
   removed the file, which is the `FileNotFoundError` the second run hit on its final rename.

The timing, not `DEPLOY_DB=1`, is the difference with the 02:48 dump that worked: that one did not
overlap a Watchtower session. `DEPLOY_DB=1` still recreates `db` only in step (c), after a verified
dump (bug report 094).

Two more ways to get a second writer existed next to it: the fallback started without checking that
the failed run's container, or any other `db-backup` container (the nightly timer's), was gone; and
`tools/db_backup.py`'s nightly prune deleted every `.partial` file in the directory, including one a
dump in progress was still writing.

# solution

One dump writer at a time, each with a file of its own:

- `scripts/deploy.sh` runs the service with its own `--name` and
  `-l com.centurylinklabs.watchtower.enable=false`, and `docker/docker-compose.backup.yml` sets the
  same label on `db-backup` and `db-restore-check` for the timers.
- After a failed run the deploy removes that container with `docker rm -f` and waits until
  `docker inspect` no longer finds it; if it is still there after
  `PREDEPLOY_BACKUP_RM_WAIT_SECONDS` (default 60) the deploy is refused rather than starting a
  second writer. Any other running `db-backup` container refuses the fallback as well.
- The fallback writes `muma_db_pre-deploy_<stamp>_fallback.sql.gz` through
  `muma_db_pre-deploy_<stamp>_fallback.<pid>.sql.gz.partial`; `tools/db_backup.py` writes through
  `<name>.<hostname>-<pid>.sql.gz.partial` (inside a container the host name is the container id).
  Both still match the pre-deploy rotation and the partial sweep.
- `tools/db_backup.py`'s prune only removes a partial file that has not been written for an hour; a
  live dump writes continuously and the stall watchdog stops a silent one after five minutes.
- The fallback's stall watchdog already measured file growth; a test now pins that a slow but
  growing dump is not stopped.

Tests: `tests/ci/test_deploy_script_hygiene.py` reproduces the incident with the fake docker -- a
failed run leaves a "container" that keeps writing into the pre-deploy partial files. Against the old
script that test fails with the same `gzip` refusal as production; with the fix the container is
removed before the fallback's dump starts and the dump verifies. Further tests cover a container
that will not go (refused, no dump), another running `db-backup` (refused), the unique names, and a
slow-growing dump. `tools/test_db_backup.py` covers the per-writer partial names and the prune age
gate; `tests/ci/test_backup_compose_standalone.py` the compose label.

Left open: Watchtower's own scoping (#68, now with this evidence), reinstalling the backup compose
file on the host so the timers get the label, and retrying the `DEPLOY_DB=1` deploy (#106).
Tracked in #104.
