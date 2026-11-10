# GetSongBPM As An Octave Prior — Technical Design

Implements [functional.md](functional.md), GitLab issue #152. Builds on
[bpm-octave/technical.md](../bpm-octave/technical.md): one more term in `octave.choose_octave`.

## Data Model

Declared in `services/common/schema_tables.py`; the deploy's `schema_reconcile` adds both.

New `getsongbpm_lookups`, one row per song asked about:

| Column | Type | Meaning |
|---|---|---|
| `lookup_key` | CHAR(64) PK | SHA-256 of `"<artist>\t<title>"`, both normalised (`getsongbpm.lookup_key`): first credited artist, bracketed parts and a featuring tail dropped, accents folded, lower case, letters and digits only. |
| `artist`, `title` | VARCHAR(255) | The search terms, for a person reading the table. |
| `status` | ENUM('ok','not_found') | A transient failure is not stored. |
| `bpm` | DECIMAL(5,2) NULL | The listed tempo (40-250), NULL for `not_found`. |
| `song_id`, `song_url` | VARCHAR NULL | GetSongBPM's id and song page. |
| `fetched_at` | DATETIME | A `not_found` is due again after `NOT_FOUND_RETRY_DAYS` (90). |

`library_track_bpm` gains `external_bpm` DECIMAL(5,2) NULL: the GetSongBPM tempo the octave choice
weighed, NULL when the term did not apply. The worker and the refold write it with the other fold
columns, and a refold that no longer applies it clears it.

## The term (`octave.py`)

- `weak_priors(evidence)`: the root folder is in `MAINSTREAM_ROOTS` and neither the label nor the
  artist prior has any weight. Only these tracks are looked up, and only for these the cached tempo
  is read (`getsongbpm.evidence_prior`, called from `refold.evidence_from`).
- `Evidence.external`: `Prior.around(listed, EXTERNAL_SPREAD = 0.12)`.
- `external_prior(evidence, raw)`: the prior, but only when the listed tempo lies within
  `EXTERNAL_MATCH` (0.12 octave, about 9%) of raw, raw/2 or raw×2. Otherwise it is another
  recording and ignored.
- Term `getsongbpm`: `−1.5 · min(4.5, ½z²)`, like a well-sampled label. It counts as evidence (the
  neutral prior drops to 0.3), it can vouch for a doubling above 205 (`_vouched`), and it is not in
  `WEAK_EVIDENCE`, so a fold it decides is not capped at 0.6.
- `Choice.external_bpm`: the listed tempo when the term applied.

`FOLD_VERSION` stays 2: with the key empty every outcome is unchanged.

## The lookup (`bpm/getsongbpm.py`)

- Request: `GET https://api.getsongbpm.com/search/?api_key=<key>&type=both&lookup=song:<title>
  artist:<artist>` with the shared User-Agent (`user_agent('muma-bpm-analyzer', ...)`).
- Parsing (`parse_search`), tolerant: `search` is a list of songs, or an object with `error` when
  nothing matched. The first song whose normalised title equals the searched one and whose artist
  is the searched one (or contains it as a word run) and whose `tempo` (string or number) lies in
  40-250 wins.
- Refusals: HTTP 429 raises `Throttled`, HTTP 401/403 or an `error` that mentions the key raises
  `KeyRejected`; both end the pass. Other failures return None and are not stored. The key is in
  the query string, so only the exception type is logged.
- Pace: one request per second for the process.
- `lookup_pass`: reads every cached key (`KNOWN_SQL`), then the measured tracks with a file under a
  mainstream root, newest first (`CANDIDATES_SQL`, one `LIKE '/mnt/music/<root>/%'` per root), keeps
  the weak-prior ones whose key is not settled, and asks about at most `PASS_BUDGET` (50) distinct
  songs. Every answer is upserted; the ids of the tracks whose song was found are returned.

## Worker (`worker.py`)

- `SETTINGS` gains `getsongbpm_api_key` (read from `config.json`, else `GETSONGBPM_API_KEY`).
- `_switch_external`: a key appearing or disappearing schedules the full refold at once; while
  empty, `self.external` is `{}`. `_maintain_priors` loads `getsongbpm.load_tempos` when on and
  passes it to `refold.refold(..., external=...)`.
- `_external_lookups` (after the pause check, every `PASS_SECONDS` = 600): one pass, then
  `refold(track_ids=found)` and a partial effective-BPM sync for them. After `KeyRejected` the next
  pass waits `KEY_REJECTED_WAIT_SECONDS` (a day) unless the key changes. A failure is logged and
  the analysis continues.
- `to_row` and `UPSERT_SQL` write `external_bpm`.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/library/tracks/by-path` | unchanged | gains `bpm_external_source`: `"getsongbpm"` when the shown tempo is a measurement whose octave was weighed on GetSongBPM, else null | unchanged |

Not breaking: one new nullable field. `effective.resolve(measured_external=...)` sets
`EffectiveBpm.external_source`; `index.INPUTS_SQL` selects `MAX(m.external_bpm) AS
measured_external`.

Config: `getsongbpm_api_key`, group BPM, `secret=True` (masked as `SECRET_SENTINEL`, never echoed).

## Cross-App Impact

- **frontend**: `trackFile.tagRows` puts `credit` (`GETSONGBPM_CREDIT`) on the BPM row;
  `TrackDetailsSheet` shows "via GetSongBPM" as a small muted link to getsongbpm.com, opened in the
  system browser. Strings `bpm.credit.via` and `bpm.credit.title`. The app bakes the web bundle, so
  phones see it with the next app release.
- **LMS / MuMa Mobile native code**: none.

## Technical Acceptance Criteria

1. `test_bpm_octave.py`: a listed 128 makes the Hazes fold `getsongbpm` and ≥ 0.75; a listed half
   time keeps a ballad at its measured octave; a listed tempo near no octave changes nothing; a
   listed 214 vouches for doubling a genre-less 107; `weak_priors`.
2. `test_bpm_getsongbpm.py`: the key's normalisation; parsing of found, `no result`, wrong artist,
   wrong title, empty or zero tempo, numbers and plain artist strings; the request's parameters and
   pace; 429, 401 and a key error; a transient failure logs no key; a pass skips settled keys,
   strong priors and non-mainstream roots, asks once per song, keeps to its budget and stops on a
   refusal.
3. `test_bpm_priors_refold.py`: the refold applies the cache only for weak priors, records
   `external_bpm`, and clears it when the cache is off.
4. `test_bpm_worker.py`: no request and no cache without a key; a pass with a key refolds and
   syncs the found tracks; the pass cadence; no pass while paused; a refused key waits a day unless
   it changes; a failed pass does not stop the round.
5. `test_bpm_effective.py`, `test_library_router.py`: `bpm_external_source` only on a measurement
   that used it. `test_router_sql.py`: the candidates, the upsert and the refold on MariaDB.
6. Frontend: `trackFile.test.js` and `trackDetailsSheet.test.js` show the link only then.

## Related Docs

- [bpm-octave/technical.md](../bpm-octave/technical.md): the octave choice and the refold.
- `services/common/store_lookup.py`: the Deezer cache this follows.
