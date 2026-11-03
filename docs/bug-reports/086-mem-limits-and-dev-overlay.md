# MariaDB, LMS and Firefox had no memory ceiling, and the dev.sh compose stack did not render

# status: fixed

# reported problem

Two leftovers from bug reports 050 and 081, both listed in the GitLab issues under "Deferred
deliberately":

1. **No memory limit on most of production.** Bug report 050 capped music-manager and the four
   workers, but `db`, `phpmyadmin`, `firefox`, the one-shot jobs and the whole `lms` stack (`lms`,
   `lms-reverse-proxy`, `lms-autoheal`) had none. They share an 8 GB host, so one runaway container
   -- a LMS scan that keeps growing, Firefox filling its shared memory -- could push MariaDB into
   the kernel's OOM killer. The limit was deferred because there was no measured basis for a
   ceiling.
2. **`scripts/dev.sh` could not start its stack.** `docker compose config` on the four files it
   layers (`docker-compose.yml`, `.workers.yml`, `.tools.yml`, `.dev.yml`) failed. README's
   "Start the entire stack" (`docker-compose.yml` + `docker-compose.tools.yml`) failed as well on
   the workstation's compose 2.26.

# Possible reason

1. The measurement had not been taken. `docker stats --no-stream` on production, 2026-09-25 17:25
   CEST (host 8 GB RAM, 5.7 GB available):

   | Container | Usage | Limit before |
   |---|---|---|
   | music-management-db-1 | 661 MiB | none |
   | lms | 549 MiB | none |
   | muma-firefox | 626 MiB | none |
   | lms-reverse-proxy | 7.6 MiB | none |
   | lms-autoheal | 8.7 MiB | none |
   | music-management-phpmyadmin-1 | 3 MiB | none |
   | music-manager | 245 MiB | 4g |
   | youtube worker | 233 MiB | 2g |
   | telegram worker | 122 MiB | 1g |

   MariaDB's own allocation, read-only from production (`SHOW GLOBAL VARIABLES` / `STATUS`): it
   runs on defaults, no `my.cnf` is mounted. `innodb_buffer_pool_size`, `key_buffer_size` and
   `aria_pagecache_buffer_size` are 128 MiB each, `Memory_used_initial` is 470 MiB. Per connection
   come `sort_buffer_size` 2 MiB, `join_buffer_size` 256 KiB and up to 16 MiB of in-memory temp
   table; `Max_used_connections` was 29 over 53 hours of uptime. (The server reports 12.3.3 while
   the compose file says 13.0: `db` has not been recreated since that bump, which is the same
   `DEPLOY_DB=1` gap as below.)

2. Two separate faults, each fatal on its own:
   - `docker-compose.dev.yml` added a `music-management-server` service (a bind mount of the
     frontend `dist/` into LMS's docroot). No other file in that stack defines it -- LMS is its own
     stack, `services/music-management-server/docker-compose.yml` -- so the merged service had
     neither an image nor a build context.
   - The overlays repeated `security_opt: [no-new-privileges:true]` for services
     `docker-compose.yml` already hardens. Compose 2.26 concatenates that list across files and
     then rejects the result: "security_opt array items[0,1] must be unique". Newer compose (5.x)
     and docker-compose 1.29.2 de-duplicate, which is why it never showed on production. The
     `tools` overlay did the same for `soundcloud-fetcher`, `genre-processor` and `firefox`, which
     is what broke README's base + tools as well.

   Nothing rendered a combination of files; every test looked at one file at a time.

# solution

**Memory limits**, each with its reasoning in a comment on the service and overridable in the
stack's `.env` (the table is in the operator's runbook, "Ports, logs and memory limits"):

- `db` 2g (`MUMA_MEM_LIMIT_DB`): three times what it uses and twice the ~1 GiB peak its settings
  allow at the highest connection count seen (470 MiB static + 29 x ~18 MiB). A mariadb-dump or the
  restore check adds connections, not buffer pool. Raise it together with
  `innodb_buffer_pool_size` if that is ever tuned.
- `lms` 1536m (`LMS_MEM_LIMIT`): close to three times resting; a scan or a library rebuild reads
  every tag on top of SQLite's page cache and the Wt threads. Written as `1536m` rather than
  `1.5g` so no compose version has to parse a fraction.
- `firefox` 2g (`MUMA_MEM_LIMIT_FIREFOX`), more than the 1.5g first proposed: its `shm_size` is
  1 GB, and tmpfs pages are charged to the container's memory cgroup, so a limit below
  shm plus the browser could OOM-kill Firefox exactly during a YouTube re-login.
- `phpmyadmin` 256m; `lms-reverse-proxy` and `lms-autoheal` 128m each (measured under 10 MiB).
- One-shots (`soundcloud-fetcher`, `genre-processor` in the main file, `release-date-backfill`,
  `song-work-repair` in the tools file) 1g (`MUMA_MEM_LIMIT_ONESHOT`), half the downloader
  worker's ceiling for the same kind of work; `db-backup` and `db-restore-check` 512m
  (`MUMA_MEM_LIMIT_BACKUP`), since both stream through gzip and the heavy side runs in `db`.

`mem_limit` is the key the files already use; all of them render with docker-compose 1.29.2
(`docker run --rm -v "$PWD":/w -w /w docker/compose:1.29.2 -f <file> config`), and the rendered
output carries every limit. The `lms` file has no `version:`, which 1.29.2 reads as the Compose
Specification, where `mem_limit` is valid too.

**Applying them:** a limit only applies to a container created after the change. The next deploy
recreates music-manager, the workers and the `lms` stack; phpMyAdmin and Firefox only when their
image changes; the one-shots when next run. `db` needs a `DEPLOY_DB=1` deploy -- already in
the GitLab issues for the log rotation of bug report 081, and that line now names this as well.

**dev.sh overlay:** `docker-compose.dev.yml` no longer names the LMS container. The overlays
(`workers`, `tools`, `dev`) no longer repeat `image` and `security_opt` for services
`docker-compose.yml` defines; they inherit both, so the rendered services are still hardened (checked
in the `config` output). Dropping `image` from those entries also removes their
`writable-filesystem-service` SAST findings (workers x4, tools x5 to x2), so
`security/accepted-sast-findings.txt` shrinks accordingly; semgrep's `no-new-privileges` rule only
fires on a service with an `image`, so nothing new is reported.

**Test:** `tests/ci/test_compose_render.py` renders every documented combination -- production, the
`lms` stack, the backup file, base + tools, the four `dev.sh` files, and the standalone core, full
and test files. Statically with PyYAML (every merged service has an image or build; `security_opt`,
`cap_add`, `cap_drop` and `dns` stay unique once merged), and with `docker compose config -q` where
the compose v2 CLI is installed, skipping that half with a message where it is not (the CI Python
container). A further test fails when `dev.sh`'s file list drifts from the one tested. Against the
files before this fix, five of its cases fail: dev.sh and base + tools, statically and rendered.
