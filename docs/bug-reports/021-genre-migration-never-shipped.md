# Genre Curation Migration Never Reached Production (.gitignore swallowed it)

# status: fixed

# reported problem
After release 0.0.52 the Genre Curation page in the management UI returned an error in production,
while every job in the release pipeline had been green and `deploy:prod` reported success.

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

# Notes for later
- Migrations run in step 3 of `scripts/deploy.sh`, *after* the containers are recreated in step 2.
  There is therefore a window on every deploy where new code talks to the old schema. It is short
  and self-healing, but a migration that a service cannot tolerate would need that order reversed.
- Nothing verifies afterwards that the schema matches what the code expects. A post-deploy check —
  or a startup assertion in `db_init` — would have turned this three-day-invisible failure into an
  immediately red deploy. Not implemented here; worth doing.
