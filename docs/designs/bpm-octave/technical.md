# BPM Octave Choice and Manual Override — Technical Design

Implements [functional.md](functional.md), bug report 140
([docs/bug-reports/140-bpm-octave-doublings.md](../../bug-reports/140-bpm-octave-doublings.md)).
Replaces the "Octave folding" section of [bpm-browse/technical.md](../bpm-browse/technical.md) as the
decision; `bands.py` stays as a fallback prior.

## Data Model

`migrate_v53_bpm_octave.sql` (+ CREATE TABLE / `ADD COLUMN IF NOT EXISTS` in
`services/common/db_init.py`, `tests/integration/test_schema.py`):

`library_track_bpm` gains:

| Column | Type | Meaning |
|---|---|---|
| `raw_confidence` | DECIMAL(4,3) NULL | The estimator's pulse confidence (0..1). NULL on rows from before; the refold fills it from `confidence`. |
| `strength` | FLOAT NULL | Comb score of the raw estimate. NULL until re-measured. |
| `half_score`, `double_score` | FLOAT NULL | Comb scores of raw/2 and raw×2 (30-500 BPM). |
| `fold_evidence` | VARCHAR(16) NULL | Which term decided: `estimate`, `label`, `artist`, `genre`, `band`, `path`, `neutral`, `getsongbpm`; `unsettled` for a raw estimate above 205 that no evidence settles (issue #153); `manual`. |
| `fold_margin` | FLOAT NULL | Winner minus runner-up, log-score units; < 1 is ambiguous. |
| `fold_version` | SMALLINT NULL | `octave.FOLD_VERSION` of the rule that chose. |

`confidence` changes meaning: `raw_confidence × certainty(margin)`, `×0.9` when folded, capped at
0.6 when the fold was decided by `neutral` or `path` alone. `bpm` is the chosen octave, `raw_bpm`
the estimate, `octave_corrected` = chosen ≠ raw.

New `library_bpm_priors` (`kind` label/artist/genre, `prior_key` id or lower-cased genre name,
`centre` = mean log2 BPM, `spread` = std in octaves, `samples`, `updated_at`; PK (kind, prior_key)).
Derived, rewritten daily.

New `library_track_bpm_manual` (`track_uid` PK, `bpm`, `set_by` user id, `set_at`). Keyed on
`track_uid` so a library rebuild keeps it.

`library_track_effective_bpm.source` ENUM gets `'manual'` appended (metadata-only ALTER, listed in
`tests/ci/test_migration_ordering.py` REVIEWED_SAFE).

## The octave choice (`services/music_manager/bpm/octave.py`)

Candidates: raw × {1, ½, 2} within 40-500. Score = sum of terms (natural-log units):

| Term | Value |
|---|---|
| estimate | +0.35 for the raw estimate; for a neighbour with known comb scores `1.5·ln(r) + 10·min(0, ln(r/0.6))`, r = neighbour score / estimate score (≤ 1). On the evaluation set a correct neighbour scored ≥ 0.64; The Silence's 230 scored 0.47. |
| label | `−w·min(4.5, ½z²)`, z = distance in log2 over max(spread, 0.12); w = 1.5·n/(n+20), only n ≥ 10 and spread ≤ 0.45. The best-sampled of the track's labels. |
| artist | same, w = 1.5·n/(n+10), n ≥ 5. |
| genre / band | the most specific (narrowest) of the track's genres: its learned prior when n ≥ 30 (w = 1.5·n/(n+30)), else its `bands.GENRE_BANDS` band read as a Gaussian with the edges at 1σ (w = 0.9). |
| path | root folder in {Hitzone, Spotify, Lidarr, Top 100, Top-100}: prior 105 BPM, spread 0.4, w = 1.0 (0.5 with a genre). |
| neutral | prior 135 BPM, spread 0.5, w = 1.0 without genre/label/artist evidence, else 0.3; plus −0.8 for a candidate above 205 or below 70 unless the track's own genre or label is closer to it than to its octave. |

Hard rules: a doubled candidate above 205 exists only when the track's own genre or label is closer
to it than to the raw estimate (`_vouched`). A raw estimate above 205 is only halved when a real prior
is closer to the half than to the estimate (`_halving_vouched`, see "Halving needs real evidence").
Certainty = 1 − ½·e^(−1.2·margin).

Tuning: the weights were set on the ground-truth set (tools/bpm_eval.py, 399 genuine tags) and a
read-only 10% sample of production (26,789 measured tracks) with production's learned priors.
Ground truth: 84.5% → 84.7% within 1 BPM (the octave-oracle ceiling is 84.7%); genre tracks 82.4% →
82.4%. The sample: 3.9% of tracks change tempo; above 200: 4,678 → 3,968.

## Halving needs real evidence (issue #153, `FOLD_VERSION` 3)

Functional numbers and the measurement: [functional.md](functional.md), "Change: A Halving Needs
Real Evidence".

- `_real_priors(evidence, genre, raw)`: the track's genre (learned or band), label and artist when
  their weight is not zero, the GetSongBPM prior when it matches an octave, and the path prior for a
  mainstream root. Not the neutral prior.
- `_halving_vouched`: one of them is closer to raw/2 than to raw. `choose_octave` still scores the
  half, so the margin of a kept estimate is what it was; it only refuses to let an unvouched half
  win. When it would have won, the result is the raw estimate with `evidence = 'unsettled'` and
  `margin = 0`.
- `_estimate_supported`: one of them is closer to raw than to raw/2, or the half's comb score is
  below `AUDIO_KNEE` (0.6) of the estimate's. A raw estimate above 205 that wins without this is
  `unsettled` too.
- `weak_value(octave_corrected, fold_evidence)`: `unsettled`, or a fold decided by `neutral` or
  `path`. The confidence of a weak value is capped at `WEAK_FOLD_CAP` (0.6); an unsettled one has
  the certainty of a tie, so it is at most half the pulse confidence.
- `FOLD_VERSION` 3: the bpm-analyzer's `_maintain_priors` refolds every `ok` row at start, so the
  re-evaluation of the old halvings needs no script. Every row gets the new `fold_version`; only
  rows whose outcome changed get a new `bpm`. The writeback has nothing due until that refold ran.

Dry run on production's rows (2026-11-12, 115,077 rows with raw above 180 or folded, production's
priors): 3,127 old halvings back at their raw estimate (3,124 `unsettled`), 1,082 still halved (937
decided by `neutral` with a real prior on the half's side, 145 by `path`), no other `bpm` change,
no change in which rows are reliable.

## Priors (`priors.py`)

`PRIORS_SQL` per kind, one statement each: training rows are `status = 'ok'`,
`COALESCE(raw_confidence, confidence) ≥ 0.75`, value `LOG2(raw_bpm)` (never the folded value), and
`raw_bpm` in 88-200, or the track has a `HARD_GENRES` genre (band above 200), or -- artists only --
the track has no genre and no file under a mainstream folder. Artist rows exclude titles matching
`REMIX_PATTERN` (bracketed remix / bootleg / rework / flip / VIP / re-edit / style words). Trimmed
once: mean per key, then mean and std over rows within 0.5 octave of it; keys with fewer than 5 rows
are dropped. Stored with upsert + prune per kind. Production on 2026-09-30: 568 label priors, ~4.4k
artist priors, 113 genre priors; 81.9% of measured tracks have a label or artist prior.

The window 88-200 keeps half-time readings (a 75 hardstyle, an 87 drum 'n bass) and doubled pop
(234) out. Extending the >200 rows to labels made one uptempo label double its own 130 BPM tracks,
so labels keep the plain window.

## Worker (`worker.py`) and refold (`refold.py`)

- `to_row` runs `choose_octave` with `refold.evidence_from` (genres, labels, primary artist from
  `EVIDENCE_SQL`, root from the path) and stores every new column. The old artist-genre fallback
  (`ARTIST_GENRES_SQL`) is gone.
- The queue has three tiers, each `ORDER BY t.id DESC`, filled in order: (1) no current measurement
  (as before); (2) `strength IS NULL AND (bpm > 200 OR bpm < 70 OR octave_corrected = 1 OR
  fold_margin < 1)`; (3) `strength IS NULL`. Estimated on production: tier 2 ≈ 33% of rows (~89k,
  ~6 h at 12-17k/h), tier 3 the other ~180k (~12 h). `method` stays `acf-comb-v1`: the estimate
  itself did not change.
- `_maintain_priors` at start and every `PRIORS_SECONDS` (a day): recompute the priors when the
  stored ones are a day old (else load them), then `refold.refold` every `ok` row from
  `FOLD_INPUTS_SQL` (streamed), writing only rows whose outcome changed (`UPDATE ... WHERE
  raw_bpm <=> %s`, so a concurrent re-measure wins). A refold that wrote anything triggers the full
  effective-BPM sync. Failures are logged and retried after `IDLE_SECONDS`.
- Dry run by hand, writes nothing (not even the priors):
  `docker exec muma-bpm-analyzer python -m services.music_manager.bpm.refold --dry-run --sample 20`.

## Effective BPM (`effective.py`, `index.py`, `effective_table.py`)

`resolve(manual=...)`: a valid manual value wins as `source = 'manual'`, `confidence = 'high'`,
not folded, not approximate. `INPUTS_SQL` selects `MAX(mb.bpm) AS manual` from
`library_track_bpm_manual`, so the browse index, the materialised table and the details sheet all
see it. The measured value's `high`/`medium` still compares the stored `confidence` (now
octave-aware) with `bpm_reliable_confidence`.

## Tag writeback (`tag_writeback.py`)

`DUE_SQL`: value `COALESCE(manual.bpm, b.bpm)`; due when a manual value exists, or when
`fold_version = FOLD_VERSION`, the value is not weak (`NOT (fold_evidence <=> 'unsettled' OR
(octave_corrected = 1 AND fold_evidence IN ('neutral', 'path')))`, the SQL form of
`octave.weak_value`, issue #153) and (`confidence ≥ min` or `tag_action = 'written'`), and
`NOT (tag_bpm <=> value)`. So nothing is written before the deploy's refold has run; a file the step
wrote is rewritten whenever its value changes (the ~835 doubled tags, confident or not: the old value
came from a rule that was wrong); a manual tempo is always written. `RECORD_SQL` stamps the value
that was read and only while it is still the current one. A manual tempo on a track without a
`library_track_bpm` row is written once the track is measured.

**Un-pausing.** Safe as soon as the bpm-analyzer logged its first `bpm: refolded N measurements`
after the deploy (minutes): from then on every due row was decided by this rule. Waiting for tier 2
(~6 h) additionally lets the audio evidence settle the ambiguous rows first, so fewer files are
written twice.

## API Contract

Router `/api/library/bpm` (`services/music_manager/routers/bpm.py`), permission `bpm.override`
(new in `rbac.PERMISSIONS`, granted to admin, not to the user role).

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `PUT /tracks/{track_id}/manual` | `{"bpm": 40..500}` or `{"factor": 0.5 \| 2}` (on the tempo shown now) | `{track_id, bpm, bpm_source, bpm_confidence, bpm_folded, bpm_approximate, measured_bpm, raw_bpm}` | 400 neither/both, or result outside 40-500; 404 no such track; 409 factor on a track without a BPM; 422 other factor; 401/403 no key / no permission |
| `DELETE /tracks/{track_id}/manual` | -- | same | 404; 401/403 |

Both audit (`bpm.manual_set` with `{track_id, bpm, factor, previous_bpm, previous_source}`,
`bpm.manual_cleared` with `{track_id, previous_bpm}`), sync `library_track_effective_bpm` for the
track and mark the browse index stale. `/api/library/advanced` rows gain `bpm_source`. No breaking
change: every existing field keeps its shape; `bpm_source` gains the value `manual`.

## Cross-App Impact

- **frontend**: `BpmOverride.svelte` in the management `TrackInspector` and the player's
  `TrackDetailsSheet`; `bpm.js` helpers; the "handmatig" marker; `bpm.source.manual` string. Needs an
  app version bump at release.
- **LMS / MuMa Mobile**: none. LMS reads the tag the writeback writes (issue #150); the app shows
  MuMa's effective BPM, which now can be `manual`.

## Technical Acceptance Criteria

1. `test_bpm_octave.py`: Hazes (no genre, Hitzone, no artist prior) → 128 and ≤ 0.6; Hazes at 131.81
   stays; an artist prior alone never doubles 128 to 256; a genre-pure label doubles a genre-less 105;
   The Silence with scores → 115 and ≥ 0.75, without scores → 115 and ambiguous; genre-less 215 with
   a strong fast pulse stays, without → 105 and ≤ 0.6; Spotify 234 → 117; half-time hardstyle → 150
   and ≥ 0.75.
2. `test_bpm_priors_refold.py`: every priors value bound; remixes out for artists only; the remix
   pattern on production titles; recompute upserts and prunes; refold turns the Hazes row into 128,
   keeps `raw_confidence`, writes nothing twice, uses stored scores; the dry-run CLI refuses to write.
3. `test_bpm_worker.py`: the three tiers; `to_row` fills every column; priors maintenance cadence,
   recompute when old, full sync after a writing refold, retry after a failure.
4. `test_bpm_manual.py`: ½×/2×/set/clear, audit, sync, 400/404/409/422, 403 without the permission,
   manual precedence in `effective.resolve`.
5. `test_bpm_tag_writeback.py` + `test_router_sql.py`: fold-version gate, manual value written, a
   written file requeued unconfident, record stamps the value read; priors/refold/override end to end
   on MariaDB; `test_schema.py`: tables, columns, ENUM.

## Related Docs

- [bpm-browse/technical.md](../bpm-browse/technical.md) — estimator, worker, effective BPM.
- [bpm-tag-writeback/technical.md](../bpm-tag-writeback/technical.md) — the writeback.
- `tools/bpm_eval.py` — method `ours_octave` runs this rule (genres + path only) on a TSV sample.
