# ML Analyzer — Technical Design

See [docs/designs/README.md](../README.md) for the design-doc process this document follows. This
implements the already-agreed [functional.md](functional.md). Implemented in
`services/ml-analyzer/analyzer.py` (feature extraction and CLI worker), `services/ml-analyzer/trainer.py`
(model training), `services/ml-analyzer/predict.py` (single-file genre prediction), and
`services/ml-analyzer/approve.py` (interactive CLI review tool). See [Related Docs](#related-docs) for the
database and architecture references this design builds on.

## Data Model

Tables live in the shared `music_management` MariaDB database, defined in
`services/common/db_init.py` (`ensure_tables_exist`) and mirrored in `services/ml-analyzer/db_init.sql`:

`library_track_audio_features` (one row per analyzed file, keyed by `track_id`):

| Column | Required? | Notes |
|---|---|---|
| `track_id` | `PRIMARY KEY` | either the internal `library_tracks.id` (as a string) when known, or a SHA-256 hash of the absolute file path (`TrackAnalyzer.get_track_info`) when the track can't be matched to `library_media_files` |
| `internal_track_id` | optional, `FK → library_tracks.id ON DELETE SET NULL` | backfilled by `migrate_paths.py` for legacy rows keyed by hash only |
| `file_path` | optional | absolute path at analysis time; not kept in sync if the file is later moved (see [Open Questions](functional.md#open-questions--not-yet-decided)) |
| `tempo`, `duration`, `mean_*`/`std_*` spectral/RMS/ZCR/chroma columns, `mfcc_1..13`, `std_mfcc_1..13` | populated by `TrackAnalyzer.extract_audio_features` (Librosa) | `NULL` when `--tags-only` was used (no audio decoding) |
| `artist_name`, `label_name`, `release_year`, `source_platform`, `bpm_tag`, `genre_tag` | populated by `TrackAnalyzer.extract_metadata` from file tags (ID3/FLAC/MP4) and folder structure (`Soundcloud`/`Youtube`/`Telegram`/`EPs/<label>`) | used as training metadata features and as a genre fallback when no ML label exists |
| `musical_key`, `energy`, `danceability`, `valence`, `popularity` | schema column exists; **never written by any current code path** | placeholders for the not-yet-implemented Musical Key/Mood detection (see functional design's Open Questions) |

**Invariant**: `UNIQUE (track_id)` — `TrackAnalyzer.save_features` always upserts
(`INSERT ... ON DUPLICATE KEY UPDATE`), so re-analyzing a track never creates a duplicate row.

`library_track_ml_labels` (one row per track's *training* label, keyed by `track_id`):

| Column | Required? | Notes |
|---|---|---|
| `track_id` | `PRIMARY KEY`, same value space as `library_track_audio_features.track_id` | no `FOREIGN KEY` between the two tables — joins are by value, not by DB constraint |
| `ml_genre` | optional | initialized from `genre_tag` on first save; overwritten by a human reviewer via `approve.py` |
| `ml_review_status` | `ENUM('unreviewed','human_verified','borderline','do_not_train')`, default `unreviewed` | only `human_verified` rows (or `approved_for_training = 1`, see below) are used for training by default |
| `approved_for_training` | `BOOLEAN`, default `FALSE` | set to `1` by `approve.py` on approval or correction, `0` on "do not train" |
| `internal_track_id` | optional, `FK → library_tracks.id ON DELETE SET NULL` | present in `services/common/db_init.py`'s definition; not populated by any current `ml-analyzer` code path |

`library_track_ml_predictions` (append/upsert per track, one row per `track_id` in practice since
`predict.py` upserts on `track_id`):

| Column | Notes |
|---|---|
| `track_id` | matches `library_track_audio_features.track_id` |
| `model_version` | hardcoded `'v1.0-rf'` in `predict.py`; not derived from the trained model artifact |
| `predicted_genre`, `confidence_genre` | written by `GenrePredictor.save_prediction` |
| `predicted_subgenre`, `confidence_subgenre`, `predictions_json` | columns exist in `db_init.sql`; **never populated** by `predict.py` (single top-genre prediction only) |

Cross-references: `library_tracks`, `library_media_files` (see
[docs/database-design.md](../../database-design.md) for the full library schema) and
`rules_subgenre_hierarchy` (used by `trainer.py` to fold subgenres into parent genres before training).

## API / CLI Contract

There is no REST API for `ml-analyzer` — no `/api/ml*` route exists anywhere under `services/music_manager/`
(confirmed by search). All entry points are standalone CLI scripts, each loading DB credentials from the
environment via `python-dotenv` / `ConfigStore`:

| Script | Invocation | Behavior |
|---|---|---|
| `analyzer.py` | `python analyzer.py <path> [--save] [--parallel] [--tags-only]` | analyzes a single file or every supported file (`.mp3/.flac/.wav/.m4a/.ogg`) under a folder |
| `analyzer.py` | `python analyzer.py --all [--save] [--parallel] [--tags-only] [--repeat] [--sleeptime N]` | `TrackAnalyzer.run_full_scan`: walks the fixed set of library subfolders (`EPs`, `Soundcloud`, `Youtube`, `Telegram`, `Livesets`, `Podcasts`, `Top 100`, `Warm Up Mixes`) under `$MUSIC_PATH`; `--repeat` turns it into a long-running worker sleeping `--sleeptime` seconds (default 3600) between passes — this is the process the `ml-analyzer` Docker container was built to run continuously; that service is commented out of `docker/docker-compose.yml`, so nothing runs it today (see `docs/open-work.md`, "ml-analyzer: retire it or repair it") |
| `trainer.py` | `python trainer.py [--test]` | pulls `human_verified` (or, with `--test`, all `approved_for_training`/tag-fallback) rows via `TrackAnalyzer.get_training_data`, trains a `RandomForestClassifier` (with `GridSearchCV`), and writes `models/genre_classifier.joblib`, `models/label_encoders.joblib`, `models/feature_scaler.joblib` |
| `predict.py` | `python predict.py <path_to_audio_file>` | loads the trained model, re-analyzes the file (features only, not saved), predicts a single top genre + confidence, and upserts it into `library_track_ml_predictions` |
| `approve.py` | `python approve.py [--redo] [--limit N]` | interactive terminal review loop: prints file/artist/label/audio-feature summary plus an AI genre guess (if a model is present) for tracks with `ml_review_status = 'unreviewed'`, and updates `library_track_ml_labels` per the reviewer's `y`/`n`/`s`/`q` choice |
| `migrate_paths.py` | `python migrate_paths.py` | one-off backfill: joins `library_track_audio_features` to `library_media_files` on the legacy hash key to populate `file_path`/`internal_track_id` for rows created before that join existed |
| `fix_db_schema.py` | `python fix_db_schema.py` | `ALTER TABLE`-based schema-repair script for `library_track_audio_features`, referenced by `migrate_paths.py`'s own error message when columns are missing |

There is no error-response contract to document (no HTTP layer): failures are printed to stdout/stderr and
the script either skips the file (`analyze_folder`'s per-file `try/except`) or exits non-zero
(`sys.exit(1)` in `analyzer.py` when no path/`--all` is given).

## Cross-App Impact

- **`music-manager`**: `services/music_manager/routers/library.py` (`GET /api/library/advanced`,
  `GET /api/library/tracks`) reads `library_track_audio_features` (`tempo`/`bpm_tag`, `musical_key`,
  `energy`) and `library_track_ml_labels.ml_genre` directly via `LEFT JOIN ... ON t.track_uid = af.track_id`
  — i.e. `music-manager` already depends on `ml_analyzer`'s write-side schema even though the two are
  deployed as separate containers with no shared code, only the shared database. Any column rename/removal
  in `library_track_audio_features` or `library_track_ml_labels` must be updated in both places (AGENTS.md
  rule 7).
- **`frontend`**: the "Advanced" library tab (`AdvancedLibraryTab.svelte`) surfaces `bpm`, `musical_key`,
  `energy`, and `ml_genre` as returned by the `music-manager` endpoints above; it does not call
  `ml-analyzer` directly.
- **`music-management-server` (LMS) / MuMa Mobile**: no dependency — neither reads nor writes any
  `ml-analyzer` table or endpoint.

## Technical Acceptance Criteria

1. `TrackAnalyzer.save_features` upserting the same `track_id` twice results in exactly one row in
   `library_track_audio_features` (verifies the `ON DUPLICATE KEY UPDATE` upsert, not an `INSERT`-only path).
2. `TrackAnalyzer.extract_audio_features` uses `start_bpm=150` for `librosa.beat.beat_track`, so a track at
   175 BPM is detected as 175 (or its exact double/half within tolerance), not halved to ~87 — this is the
   concrete, testable form of functional Acceptance Criterion 2.
3. `GenrePredictor.predict` returns `None` (not an exception) when no trained model is present at
   `models/genre_classifier.joblib`, so callers can distinguish "no model" from "prediction failed".
4. `TrackAnalyzer.get_training_data(min_quality='human_verified')` (the default `trainer.py` path, no
   `--test`) never returns rows whose `ml_review_status` is `unreviewed`, `borderline`, or `do_not_train`.
5. `approve.py`'s `n` choice with an empty new-genre answer sets `ml_review_status = 'do_not_train'` and
   `approved_for_training = 0`, permanently excluding that track from future training runs without deleting
   the row.

**Gap**: no automated tests exist for any of the above. `find`/`glob` over `services/ml-analyzer/` show no
`tests/` directory, no `test_*.py` files, and no references to `ml-analyzer` in
`docs/testing-inventory.md`'s per-module test commands. Per AGENTS.md rule 1 ("every new feature or bug fix
includes corresponding tests"), this is a pre-existing gap for this already-implemented feature; a follow-up
change adding a `services/ml-analyzer/tests/` suite (mocking the DB engine and Librosa, similar in spirit to
the `mock_base.py` pattern used by `downloader`/`importer`) should close it before further changes are made
to this service.

## Related Docs

- [docs/designs/ml-analyzer/functional.md](functional.md) — the functional design this technical design
  implements.
- [docs/database-design.md](../../database-design.md) — full library schema `ml-analyzer` reads from and
  writes into.
- [docs/architecture.md](../../architecture.md) — overall service topology and how `ml-analyzer` fits
  alongside `music-manager`, `downloader`, and `importer`.
- [docs/testing-inventory.md](../../testing-inventory.md) — per-module test commands; does not currently
  list any `ml-analyzer` tests (see Gap above).
