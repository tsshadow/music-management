- **A deploy no longer hangs for an hour on a migration waiting for a table lock.** The 0.73.1
  deploy re-ran `migrate_v29`, a no-op `ALTER TABLE tagger_processed_files MODIFY COLUMN mtime DOUBLE`.
  It queued behind a five-hour diagnostic query and waited until the job timed out. While it
  waited, every tagger write to that table froze for three hours, and the retry's pre-deploy dump
  queued behind it too. Each migration now runs with a 120 s `lock_wait_timeout` through the new
  `tools/apply_migrations.py`. A blocked one errors, naming the file, prints the server's sessions
  so the lock holder is visible, and stops the deploy before any container is recreated. A new
  `schema_migrations` ledger records every applied file with its sha256, so an unchanged file is not
  run again (a changed one is). Migrations run in explicit byte-wise name order (`v10` before `v2`).
  The pre-deploy dump now stops after five minutes without output instead of hanging, and in that
  case the deploy does not start a second dump that would queue behind the same lock. See bug
  report 068 and `docs/deployment.md`, "When a deploy stops on a lock wait".

<!-- release notes -->

- **Deploys:** a database migration blocked by another session now stops the deploy after two
  minutes, showing who holds the lock, instead of hanging it for an hour. Migrations that already
  ran are skipped.
