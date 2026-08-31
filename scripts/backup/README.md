# Database backups

Implements `docs/superpowers/specs/2026-08-02-daily-db-backups-design.md`. Read
that for the reasoning; this is the operating manual.

Three timers, one job each:

| Timer | When | What it does |
| --- | --- | --- |
| `muma-db-backup` | nightly 03:12 | dump, verify, record row counts, prune |
| `muma-db-backup-stale` | daily 09:12 | alert when the newest dump is over `BACKUP_STALE_AFTER_HOURS` old |
| `muma-db-restore-check` | Sunday 05:30 | restore the newest dump into a throwaway database and compare it against the recorded row counts |

## Why a restore check, and not just a checksum

A dump that gunzips and ends in `-- Dump completed` is intact. That is not the
same as restorable, and it is a long way from complete. The backup job writes
`latest.json` next to the dumps with an exact `COUNT(*)` per table, and the
restore check asserts the restored copy has the same tables with the same rows.
That is the difference between "a file arrived" and "the database is recoverable".

The comparison allows a table to come back with up to 2% fewer rows (small tables
are compared exactly). That is arithmetic, not slack: `--single-transaction`
snapshots at the start of the dump and the counts are read when it finishes, so an
append-heavy table legitimately restores slightly short. A lost table, an emptied
one, or a truncated file all fall far outside it.

## Why the staleness check exists twice

The design named this gap and left it open: *"a cron job that stops running
altogether produces no failures and therefore no alerts"*. It then happened —
nothing ran between 23 July and 31 August 2026, and nobody noticed.

So it is checked from both sides:

- `muma-db-backup-stale.timer` pushes an alert. Fast, but blind in exactly the
  case where its own timer is the thing that died.
- `GET /health/backup` on music-manager reports the age and returns **503** when
  it is over the limit. Point an Uptime Kuma monitor at it. That monitor runs
  somewhere else, so it still fires when everything on this host has stopped.

Neither alone is enough. The endpoint is deliberately separate from `/health`:
a stale backup is a real problem but not a service outage, and merging them
raises the wrong alarm on the wrong channel.

## Install

On the host that runs the stack, as root:

```bash
scripts/backup/install-systemd.sh /path/to/repo/.env
```

It refuses to install when `HOST_BACKUP_PATH` sits on the same device as
`HOST_DATA_PATH/mariadb`. That is not pedantry — it is the state production was
in: `/muma/backups` and the data directory were different paths on one disk, so
every dump ever taken would have died with the thing it was protecting.

On the Proxmox containers the backup share needs a mount point first:

```bash
pct set 107 -mp3 /mnt/pve/smb-backups,mp=/mnt/backups && pct reboot 107
```

## The database account

The dump runs `--routines --triggers --events`, which the application user
(`music-management`) cannot do: it holds `SELECT, INSERT, UPDATE, DELETE, CREATE,
ALTER` on `*.*` and no `SHOW VIEW`, `TRIGGER` or `EVENT`. Rather than handing the
job the root credential, create a read-only account and put it in
`BACKUP_DB_USER` / `BACKUP_DB_PASS`:

```sql
CREATE USER 'muma-backup'@'%' IDENTIFIED BY '<generated>';
GRANT SELECT, SHOW VIEW, TRIGGER, EVENT, LOCK TABLES, PROCESS ON *.* TO 'muma-backup'@'%';
-- Only for the restore check, which builds and drops its own database:
GRANT CREATE, DROP, INSERT, ALTER, REFERENCES, INDEX ON `music-management_restore_check`.* TO 'muma-backup'@'%';
FLUSH PRIVILEGES;
```

Leaving those unset falls back to `DB_USER`, and the dump then fails loudly on
the first missing privilege rather than quietly dumping less than it was asked
for.

## Restoring, by hand

```bash
scripts/restore_db.sh /mnt/backups/muma/muma_db_20260901_031200.sql.gz music-management-restored
```

The target is a required argument with no default, and restoring over `DB_DB`
needs `--force`. The dumps carry no `CREATE DATABASE`/`USE`, which is what makes
that possible.

## What is not covered

- **`apk-hoster`**, two tables on the same server, belonging to another stack.
- **The music files.** Six terabytes; see the discussion in the changelog entry.
  The rules and download archives that can re-fetch much of it *are* in this
  database and therefore are covered.
- **Point-in-time recovery.** No binlog shipping; the worst case is losing up to
  a day.
