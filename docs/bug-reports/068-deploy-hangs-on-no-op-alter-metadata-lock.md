# Deploy Hangs on a No-op ALTER Waiting for a Metadata Lock

# status: fixed

# reported problem
The `muma:deploy` job of release/0.73.1 (pipeline 3607, 2026-09-25) hung in step
"[3/5] Applying database migrations (old containers still running)" until the job's one-hour
timeout killed it. Its retry hung in step "[2/5] Pre-deploy database backup". Production stayed on
0.73.0 throughout, but the tagger stopped writing for three hours without logging anything.

Timeline (UTC):

- **2026-09-24 21:46** — a diagnostic session starts a read-only
  `SELECT COUNT(*) FROM tagger_processed_files t JOIN library_media_files m ON m.file_path COLLATE
  utf8mb4_general_ci = t.filepath COLLATE ...`: 332k × 330k rows with no usable index. It is still
  running five hours later and holds a shared metadata lock (MDL) on `tagger_processed_files` the
  whole time.
- **2026-09-25 00:00:22** — the deploy reaches `migrate_v29_processed_mtime_double.sql`,
  `ALTER TABLE tagger_processed_files MODIFY COLUMN mtime DOUBLE`. The column has been `DOUBLE` since
  that migration first ran; on the three previous deploys the statement took 0.4 s. It still needs
  an exclusive MDL, so it queues behind the `SELECT`: `Waiting for table metadata lock`.
- From then on the *pending* exclusive lock blocks every new statement on the table. 17 tagger
  `INSERT`/`UPDATE`s freeze for three hours. Nothing errors, everything waits, so no event is logged.
- **~01:00** — the job's timeout kills the `mariadb` client. The `ALTER` stays queued on the server.
- **Retry** — the deploy hangs in the pre-deploy dump: `mariadb-dump --single-transaction` reaches
  `tagger_processed_files` and queues behind the same pending `ALTER`. Its `.partial` file stops
  growing at 948 MB.
- The holder was looked for through the read-only MCP account. That account has no `PROCESS`
  privilege, so `SHOW PROCESSLIST` showed only its own sessions, and the holder was wrongly declared
  gone.
- **Fix in the field:** `KILL QUERY <holder>`, done by hand as root. The queued `ALTER` then
  completes, the tagger resumes, and a new deploy can run.

# Possible reason
Three defaults lined up:

1. **Every migration ran on every deploy.** `scripts/deploy.sh` piped every `migrate_*.sql` into the
   client on each deploy (bug report 021 made that the rule, re-runnable by design). A re-run that
   changes nothing still takes the locks the statement needs: `ALTER TABLE ... MODIFY` to the type
   the column already has needs an exclusive MDL like any other `ALTER`.
2. **Nothing timed out.** MariaDB's default `lock_wait_timeout` is 31 536 000 s (one year). The
   client waits as long as the lock is held, and once it is killed the server keeps the statement
   queued. A queued exclusive MDL request is worse than a held one: every later shared request on
   the table queues behind it, so one long read plus one no-op `ALTER` froze all writes.
3. **The dump had no timeout either.** `mariadb-dump` has no lock timeout option and no
   `--init-command` (checked against the 13.0 client: an `init-command` line in its defaults file
   is rejected as an unknown variable), so a dump that meets a queued lock waits too.

The deploy order itself (backup → migrate → up, bug report 050) was right. It is why production
never ran half-migrated: the job stopped before `up` both times.

# solution
- **Migrations fail fast.** `scripts/deploy.sh` now passes the migrations to
  `tools/apply_migrations.py`. The helper puts
  `SET SESSION lock_wait_timeout = N; SET SESSION innodb_lock_wait_timeout = N;` on the line before
  each file (N = `MIGRATION_LOCK_WAIT_SECONDS`, default 120). A blocked statement errors with 1205,
  the helper reports the file (and the line, counted in the file's own lines), prints the server's
  processlist as root (Id, User, Time, Command, State, the start of any open InnoDB transaction,
  and Info cut to 100 characters, with statements that mention a credential left out), and the
  deploy stops before `up`. The password travels exactly as before: first line of stdin, into
  `MYSQL_PWD`, never on a command line.
- **Applied migrations are skipped.** A `schema_migrations` ledger (filename, sha256, applied_at) is
  created by `services/common/db_init.py`, declared by `migrate_v39_schema_migrations.sql`, and
  created by the helper before it reads the ledger (the first deploy reads it before new code has
  started). A file whose name and hash are recorded is skipped; a changed or unrecorded file runs,
  and is recorded after it succeeds. Every migration stays re-runnable: the ledger saves work and
  locks, it is not a correctness dependency, and a ledger that cannot be read means every file runs.
  The first deploy after this change runs everything once and fills it.
- **The order is explicit.** The helper sorts the files by name, byte-wise:
  `migrate_v10_...` before `migrate_v2.sql` before `migrate_v29_...`. Bash's glob order had depended
  on the runner's locale.
- **The dump cannot hang the job.** `tools/db_backup.py` reads the dump's output on a thread and
  stops `mariadb-dump` after `BACKUP_STALL_SECONDS` (default 300) without a byte. It names the last
  table header seen and exits 3. On exit 3 `scripts/deploy.sh` refuses the deploy instead of falling
  back to a second dump, which would queue behind the same lock. The docker-exec fallback dump got
  the same watchdog on its `.partial` file (`PREDEPLOY_DUMP_STALL_SECONDS`, default 300).
- **Tests:** `tools/test_apply_migrations.py` (skip when recorded, run when the hash changed or it is
  unrecorded, byte order, a lock timeout naming the file with the processlist, the privilege
  fallback, credential redaction); `tests/ci/test_deploy_script_hygiene.py` runs the real
  `deploy.sh` against fakes for the ledger skip, the lock timeout stopping the deploy before `up`,
  and both dump watchdogs; `tests/integration/test_migration_ledger.py` proves the ledger round trip
  and a real MDL wait timing out, with the holder in the report, against MariaDB. The e2e stack
  applies the migrations through the helper and the real client twice, and fails if the second pass
  applies anything.
- **Docs:** `docs/deployment.md` explains the ledger, the timeout, the order, and what to do when a
  deploy stops on a lock wait: find the holder in the printed processlist, `KILL QUERY` it, retry the
  job. The `PROCESS` grant for `muma-readonly` is in the GitLab issues, because it needs a person
  on production.
