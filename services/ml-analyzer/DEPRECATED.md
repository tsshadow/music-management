# ml-analyzer: deprecated

## Status

**Deprecated and disabled since 2026-09-25. The code is kept.** Decided by Teun: nobody is going to
work on this service for now, but deleting it would throw the work away. Nothing builds, deploys or
tests it by default; everything below can be undone by following [To revive](#to-revive).

What "disabled" means, concretely:

| Where | What changed |
|---|---|
| `docker/docker-compose.yml`, `docker-compose.tools.yml` | The service was already commented out; a pointer to this file sits above it. |
| `docker/docker-compose.full.yml` | Was still an active service there; now commented out the same way. |
| `build.sh` / `scripts/affected.sh` | `./build.sh` with no arguments no longer builds the image; `./build.sh ml` still does, with a warning. `scripts/ci/build-and-push-images.sh` never built it. |
| `.gitlab-ci.yml` | Out of `backend:unit`'s `changes:` list. Its only job is `backend:ml-analyzer-unit`: manual, `allow_failure`, offered only on a pipeline that touches the service or its tests. |
| `scripts/test/music-management-unit.sh` | Skips `services/ml-analyzer/` and `services/tests/MlAnalyzer*Test.py`; `scripts/test/ml-analyzer-unit.sh` runs them instead. |
| `pyproject.toml` `[tool.coverage.run]` | Omits `services/ml-analyzer/*`. Counted while skipped, it would read as ~0% covered code nobody runs. Excluding it raised the total (87.4% to ~88.5% when measured); the floor was not touched. |
| `pyproject.toml` `[tool.mypy]` | Already excluded; never type-checked. |
| `scripts/ci/dependency-audit.sh` | No longer audits `services/ml-analyzer/requirements.txt`. |
| `renovate.json` | A `packageRules` entry disables every update under `services/ml-analyzer/**`. |
| `tests/ci/test_ml_analyzer_deprecated.py` | Fails if any other CI job references the service, if the manual job stops being manual, if a compose file defines it again, or if this file disappears. |

Still on: `scripts/lint.sh` (ruff and pylint over `services/`) and `backend:format`. They cost
seconds, and they keep the kept code parseable against today's tooling, so a revival does not start
with a pile of lint. The accepted SAST findings for these files
(`security/accepted-sast-findings.txt`) stay for the same reason: the files are still in the tree.

## Why

It was not deployed, it had no owner time, and it would not have worked if it ran. The 2026-09-24
dead-code sweep (audit item A2.8) found three defects; each is re-checked here against the code.

1. **The already-analysed check reads the wrong key.** `analyze_track` checks
   `is_already_analyzed(id_for_check)` (`analyzer.py:408-409`), where `id_for_check` is the
   `library_tracks.id` whenever one exists. `is_already_analyzed` looks that value up in
   `library_track_audio_features.track_id` (`analyzer.py:343`), but `save_features` stores the
   file's path hash in that column (`analyzer.py:277`, called with `track_hash` at
   `analyzer.py:420-421`). For every file the library already knows, the skip never matches, so
   the `--repeat` loop in the Dockerfile's `CMD` re-analyses the whole library every round.

2. **The `library_track_ml_labels` key has bug report 028's stale-join shape.** The analyzer writes
   label rows keyed by the path hash (`analyzer.py:323-330`) and never fills the table's
   `internal_track_id` column (`services/common/db_init.py:142`). Every reader outside the service
   joins on the track uid instead: `routers/library.py:86` and `:344`, `routers/stats.py:64`,
   `routers/users.py:642` and `:649`, `routers/management.py:386`, and
   `track_relink.py:183` moves labels by uid. A uid compared against a path hash matches only the
   tracks the analyzer created itself (with `track_uid = path_hash`, `analyzer.py:368` and `:380`),
   not the scanner's tracks that people play -- exactly what
   [bug 028](../../docs/bug-reports/028-audio-features-cover-nothing-anyone-listened-to.md) found
   and fixed for `library_track_audio_features`, and never fixed for the labels.
   *Correction to the audit wording:* the analyzer's own training join,
   `f.track_id = l.track_id` (`analyzer.py:471-475`), is internally consistent (path hash on both
   sides); the stale key is between the analyzer and everything else that reads the labels.

3. **The predict pipeline cannot work as written.**
   - `predict.py:32-54` feeds the model 11 unscaled audio features plus four metadata columns.
     `trainer.py:97-116` and `:63-79` train it on 41 audio features scaled by a `StandardScaler`,
     plus `tempo` and six `*_boost_*` copies, and save that scaler to `models/feature_scaler.joblib`
     (`trainer.py:160`), which `predict.py` never loads. scikit-learn refuses a feature set that
     differs from the one the model was fitted on, so every prediction raises.
   - `predict.py:68` writes to `library_track_ml_predictions`, a table only
     `services/ml-analyzer/db_init.sql:41` creates. It is not in `services/common/db_init.py` and no
     `migrate_*.sql` creates it, so no deployed database has it.
   - `predict.py:64-65` keys the prediction by `library_tracks.id`, while features and labels are
     keyed by path hash: even a stored prediction would not join to its track's features.
   - Found while checking: the default training query (`analyzer.py:475`) and `approve.py:210`
     select `l.id`, a column that exists in `db_init.sql:4` but not in the shared schema
     (`services/common/db_init.py:142`, primary key `track_id`). Training and the approval CLI fail
     against the deployed database before a model is ever built.

Its compose service has been commented out of `docker/docker-compose.yml` for a long time, so none
of this ever ran in production. The unit tests passed anyway: they stub SQLAlchemy, scikit-learn and
the database, so they prove which SQL is issued, never that it matches the schema.

## What still reads its tables

`library_track_audio_features` and `library_track_ml_labels` stay, with their data. Nothing is
dropped or migrated, and every reader keeps working on the rows that exist. Without new analysis,
**the existing rows keep showing, and tracks added from now on get no audio features and no ML
genre label.**

| Reader | Uses | Without new analysis |
|---|---|---|
| `feeds/queries.py` (release radar, daily mixes) | `tempo`/`bpm_tag` as the displayed BPM; `release_date` as a fallback when `library_tracks.release_date` is NULL | New tracks show no BPM (`bpm_tag` is also only written by the analyzer). The release date comes from the servers (`release_date_sync.py`, `migrate_v24`), so feeds are unaffected. |
| `routers/analytics_filters.py`, `routers/analytics.py`, `routers/listening.py` (listening stats, analytics) | BPM filter and histogram, release-year histogram, "analysed" coverage count | New tracks fall outside BPM filters and histograms; the coverage figure only goes down as the library grows. |
| `routers/library.py` (track list and details) | BPM, ML genre | New tracks show no BPM and no ML genre. |
| `routers/stats.py`, `routers/users.py` (genre count, dynamic playlist genre filter), `routers/management.py` (recent ML activity) | `library_track_ml_labels` by track uid | Because of defect 2 these only ever matched tracks the analyzer created itself; unchanged. |
| `track_relink.py` | Moves both tables' rows to a track's new id | Unchanged. |
| `migrate_v10_audio_features_relink.sql`, `migrate_v36_schema_drift.sql` | Relink existing rows; keep the schema in step | Unchanged; they only touch existing rows. |
| `tools/integrity_check.py`, `tools/fix_nested_ep_dirs.py`, `tools/describe_tables.py` | Maintenance | Unchanged. |

## To revive

In order; each step is a merge request of its own, and the first needs a design
(`docs/designs/ml-analyzer/` holds the old functional and technical documents to start from).

1. **Fix the skip key.** Make `is_already_analyzed` look up what `save_features` writes -- better,
   key both on `internal_track_id`, the real foreign key to `library_tracks(id)` -- and add a test
   that analyses a known file twice and asserts the second call skips.
2. **Fix the label join per bug 028.** Have `save_features` fill
   `library_track_ml_labels.internal_track_id`; repoint every reader listed in defect 2 to
   `ml.internal_track_id = t.id`; add a re-runnable `migrate_*.sql` that fills
   `internal_track_id` for existing label rows by path hash and by path (the way
   `migrate_v10_audio_features_relink.sql` does for features); and cover the join in
   `tests/integration/`, because a join-key bug cannot be caught against a mocked cursor.
3. **Make predict work.** One feature-building function shared by `trainer.py` and `predict.py`,
   loading `feature_scaler.joblib`; `library_track_ml_predictions` in `services/common/db_init.py`
   plus a `migrate_*.sql` plus `tests/integration/test_schema.py` (AGENTS.md: a schema change needs
   all three); the prediction keyed like the features; the `l.id` selects replaced. Add a test that
   trains on a small fixture and predicts through the real scikit-learn, not the stub.
4. **Re-add the compose service.** Uncomment it in `docker/docker-compose.yml` (and
   `docker-compose.full.yml`), put `build_ml` back into `build.sh`'s build-all run and the `ml`
   mapping into `scripts/affected.sh`, and add the image to `scripts/ci/build-and-push-images.sh`
   so a release actually ships it.
5. **Re-enable CI.** Delete `tests/ci/test_ml_analyzer_deprecated.py`; drop the ignores from
   `scripts/test/music-management-unit.sh` and the omit from `[tool.coverage.run]`; put
   `services/ml-analyzer/**/*` back into `backend:unit`'s `changes:` and into
   `PYTHON_UNIT_SOURCES` in `tests/ci/test_gitlab_ci_policy.py`; remove the manual
   `backend:ml-analyzer-unit` job and `scripts/test/ml-analyzer-unit.sh`; re-add the requirements
   file to `scripts/ci/dependency-audit.sh`; remove the `renovate.json` rule; consider taking it out
   of the mypy exclude.
6. **Run a backfill.** Analyse the library once with `--save` against production (ask first --
   AGENTS.md rule 16), then re-measure coverage on played tracks the way bug 028 did: features and
   labels that join to tracks nobody listens to are the failure this service already had once.
7. **Update the docs**: AGENTS.md's ml-analyzer section, `docs/testing-inventory.md`, the README
   notice, this file (delete it), and a changelog fragment.
