# Standing Import Conflicts — Technical Design

See the [functional design](functional.md) and bug report
[091](../../bug-reports/091-importer-conflict-warning-spam.md).

## Data Model
New table `importer_conflicts` (`services/common/db_init.py`, `migrate_v43_importer_conflicts.sql`):

| column | type | meaning |
|---|---|---|
| `pair_key` | `CHAR(64)` PK | sha256 of `(step, source, target)`; two full paths are too long to index |
| `step` | `ENUM('renamer','mover')` | which step met it; each step prunes only its own rows |
| `source`, `target` | `VARCHAR(1024)` | full paths of the folder waiting to move and the one already there |
| `fingerprint` | `CHAR(64)` NULL | sha256 of both folders' `folder_signature` (entries, total size, newest mtime) at the last comparison |
| `first_seen`, `last_seen` | `TIMESTAMP` | when the pair was first warned about / last met |

A separate table rather than a column on `rules_label_proposals`: a conflict is a pair of folders, a
proposal is one folder and a label decision, and a renamer conflict exists before any label question
is asked.

## Behaviour
`services/importer/conflict_store.py`:

- `ConflictStore` — `snapshot(step)`, `record`, `touch`, `forget`. Every failure is logged and
  swallowed. An unreadable snapshot is a WARNING the first time in a row and DEBUG after that, and
  writes are skipped while the table cannot be read, so a database outage does not become the new
  per-cycle spam.
- `ConflictTracker(step)` — one per `Renamer`/`Mover` instance, which lives as long as the importer
  process:
  - `begin()` loads the step's rows (or keeps the in-process memory when the database is unreadable).
  - `unchanged(src, dst)` — true when the pair stands with the same fingerprint; the caller then skips
    `is_same_release` (which reads every track's length over CIFS). Logs at DEBUG.
  - `differs(src, dst)` — WARNING when the pair is new, INFO when it stood and changed; records it.
  - `same(src, dst)` — the caller parks the source; the pair is not counted as standing.
  - `end()` — forgets rows for pairs not met this cycle, logs the summary line when anything stands or
    was resolved, returns the standing count. A dry run neither records nor forgets.

`Renamer._resolve_collision` and `Mover._resolve_conflict` call the tracker around their existing
comparison; `run()` calls `begin()`/`end()`. The comparison itself and the park-on-equal policy are
unchanged.

## API Contract
New, additive: `GET /api/import-conflicts` (any authenticated account) →
`[{step, source, target, first_seen, last_seen}]`, oldest first. No existing contract changes.

## Cross-App Impact
- `music-manager`: the endpoint above.
- `frontend`: a read-only section in `LabelProposalsTab.svelte` using existing table styles (no new
  styles, so no style guide change); `nl`/`en` strings under `management.labelProposals.conflict*`.
- The importer writes the table; the music-manager only reads it.

## Technical Acceptance Criteria
- `services/importer/tests/test_importer_conflict_store.py`: once-per-pair WARNING, no re-comparison
  of an unchanged pair, no WARNING after a restart, summary line per cycle, a resolved pair forgotten
  and silent, a changed pair re-compared without a second WARNING, an equal pair parked and forgotten,
  in-process fallback without the database, per-step pruning, dry run.
- `test_importer_mover_cycle.py`: the same once-per-pair behaviour for a mover conflict.
- `test_management_router.py` and `tests/integration/test_router_sql.py`: the endpoint and its SQL.
- `tests/integration/test_schema.py`: the table is declared by both db_init and a migration.

## Related Docs
- [docs/designs/importer/technical.md](../importer/technical.md)
- Bug report 087 (crooked ` - ` folder names, 18 of the 49 pairs on 2026-09-25)
