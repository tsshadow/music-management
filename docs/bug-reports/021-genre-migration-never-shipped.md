# Genre Curation Migration Never Reached Production (.gitignore swallowed it)

# status: fixed

# reported problem
After release 0.0.52 the Genre Curation page in the management UI returned an error in production,
while every job in the release pipeline had been green and `muma:deploy` reported success.

# Possible reason
`.gitignore` line 5 is `*.sql`. The migration written for the genre curation states,
`migrate_genre_states.sql`, was therefore **never committed**: `git add -A` skipped it without
warning, `git status` never listed it, and no reviewer saw it missing from the diff. The file
existed only in the worktree it was authored in, where it had been verified twice against a real
MariaDB 10.6 container — which is exactly why nothing looked wrong.

`migrate_v2.sql` is in the repository only because it predates that ignore rule, so the existing
migration mechanism looked healthy.

Production consequently ran 0.0.52 code against the pre-0.0.52 `rules_genres` schema. Every query
touching the new columns fails there:

- `GET /api/rules/genres` selects `state`, `canonical_id`, `occurrences`, `detected_at`,
  `decided_at` and `decided_by` — none of which exist — so the curation page errors out.
- `GenreRulesHelper._preload` selects `normalized_name`, `state` and `canonical_id`, catches the
  failure and logs it, leaving an empty cache. Every genre then resolves to `unknown`, so the tagger
  silently stops writing genres instead of crashing.

A second, independent defect would have blocked the same file even if it had been committed:
`scripts/deploy.sh` applied migrations with the glob `migrate_v*.sql`, which
`migrate_genre_states.sql` does not match. Two separate silent-skip mechanisms in a row, neither of
which produces any output.

This is the same failure shape as
[007](007-telegram-session-schema-mismatch.md) and
[016](016-stale-release-branch-clobbered-latest-deploy.md): a green pipeline that provably did not
put the change into production.

# Fix
- `.gitignore` gains `!migrate_*.sql` directly under `*.sql`, so root-level migrations are committed
  while ad-hoc SQL dumps stay ignored.
- The migration is renamed to `migrate_v3_genre_states.sql`, keeping the numbered ordering that
  `migrate_v2.sql` established.
- `scripts/deploy.sh` globs `migrate_*.sql` instead of `migrate_v*.sql`, matching the `.gitignore`
  exception exactly — one naming rule now decides both what gets committed and what gets applied,
  rather than two rules that can disagree.

# Follow-up: the migration then aborted halfway on real data

Once shipped in 0.0.53, the migration ran on production and failed:

```
ERROR 1062 (23000) at line 47: Duplicate entry 'hardcore frenchcore hardmusic'
for key 'uq_rules_genres_normalized_name'
```

Production had several `rules_genres` rows differing only in punctuation — the same genre stored
three times — which cannot coexist under the new unique key on the normalized name. The migration
had been verified against seeded data covering the *semantic* edge cases (a genre both whitelisted
and ignored, a correction target without its own row, a backlog entry also ignored) but not against
duplicate spellings, which only real data had.

That left production half-migrated: the columns existed and every legacy row was `white`, but no
unique index, and the ignore list, backlog and corrections were not folded in. The curation page
worked again, while previously-ignored genres were no longer dropped, and `record_unknown` lost the
unique key it relies on to count sightings instead of inserting a new row each time.

**Worse, `muma:deploy` reported success.** The remote migration command ended with `rm
/tmp/migration.sql`, so the shell returned *that* status and the failed `mysql` was masked.

Both are fixed on `release/0.0.53`:

- The migration merges colliding rows itself instead of aborting: the lowest id survives, references
  in `rules_artist_genres`, `rules_label_genres`, `library_track_genres` and `canonical_id` are
  repointed (dropping rows that would then violate the child table's own unique key), a correction
  the survivor lacks is kept, and the merge count is printed into the deploy log. It runs unattended
  on every deploy, so requiring a manual pre-check was never a real option.
- `scripts/deploy.sh` captures `mysql`'s exit status explicitly and exits with it.

Verified against MariaDB 10.6 seeded with the production collision, including one artist, label and
track attached to two colliding genres at once: a clean run merges and completes, a second run is a
no-op with identical counts, and a run against a database left in production's exact half-migrated
state recovers to the same end state.

# Follow-up 2: what the honest exit status revealed

The very next release failed at `muma:deploy` — correctly this time:

```
ERROR 1062 (23000) at line 89: Duplicate entry 'acidcore melodic' for key 'name'
```

in **`migrate_v2.sql`**, an old migration. Every file here re-runs on every deploy, and v2 was
re-creating the unique key on `rules_genres.name` that `migrate_v3` deliberately drops in favour of
one on `normalized_name` — two rows may share a display name as long as they are different genres,
which is exactly what aliases need. So v2 undid part of v3 on every single deploy and then failed on
the data v3 had legitimately created.

It had presumably been failing for a while; nothing surfaced it while a failed migration could still
report a successful deploy.

The same block also ran `MODIFY COLUMN name VARCHAR(100)` while v3 sets `VARCHAR(255)`, silently
truncating long genre names once per deploy.

Both statements are removed from v2, which now leaves the `rules_genres` schema to v3. Verified by
running the full chain (v2, v3, v4) three times against MariaDB 10.6: identical state counts,
`name` stays `varchar(255)`, and the only unique key left is on `normalized_name`.

**The general lesson**: because every migration re-runs on every deploy, an older file is not
history — it is a statement that keeps being re-asserted. A later migration that changes something an
earlier one set up has to change that earlier file too, or the two fight on every deploy.

# Notes for later
- Migrations run in step 3 of `scripts/deploy.sh`, *after* the containers are recreated in step 2.
  There is therefore a window on every deploy where new code talks to the old schema. It is short
  and self-healing, but a migration that a service cannot tolerate would need that order reversed.
- Nothing verifies afterwards that the schema matches what the code expects. A post-deploy check —
  or a startup assertion in `db_init` — would have turned this three-day-invisible failure into an
  immediately red deploy. Not implemented here; worth doing.
