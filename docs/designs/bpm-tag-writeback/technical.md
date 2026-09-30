# Measured BPM into the file tags — Technical Design

Implements [functional.md](functional.md), issue #139. Code: `services/music_manager/bpm/tag_writeback.py`,
called from `TaggerManager.run_full` (`services/music_manager/routers/tagger.py`).

## Where it runs, and why not in the retag queue

The bpm-analyzer container mounts the music share read-only on purpose; writing files is the
tagger's job, so the writeback runs in music-manager, **as the last step of every tagger round**,
inside the tagger lock, after the retag queue (every reason: decisions, `new_in_library`, the bulk
reasons) and after the daily walk. So everything the tagger has to do goes first, and no tagger
thread writes the same file at the same time.

It does **not** put files on the retag queue (`tagger_processed_files.needs_rescan` with a new
reason), although that was the first idea:

- A queued row is a full retag. The pending pass hands it to `parse_song`, i.e. the whole rule stack
  of the file's song type, and so does the daily walk: `needs_processing` treats any flagged row as
  due. ~140k flagged files would be a full retag of half the library -- the "every deploy re-queued
  the Youtube tree" incident at four times the size -- when all that has to change is one frame.
- A reason on the row is overwritten by, or overwrites, a real decision queued for the same file.

The queue is therefore `library_track_bpm` itself (below), served by its own capped step. The tagger
round's cadence and the lock give it the same place in line a lowest-priority reason would have had.

## Data Model

`library_track_bpm` gains three columns (`migrate_v52_track_bpm_tag_writeback.sql`, the CREATE TABLE
and an `ADD COLUMN IF NOT EXISTS` in `services/common/db_init.py`, `test_schema.py`):

| Column | Type | Meaning |
|---|---|---|
| `tag_bpm` | DECIMAL(5,2) NULL | The measured `bpm` the file's tag was last reconciled with. |
| `tag_action` | VARCHAR(16) NULL | `written`, `matches`, `kept`, `missing` (file gone), `unsupported`, `failed`. |
| `tag_checked_at` | DATETIME NULL | When. |

The migration only adds columns: it marks and queues nothing (every `migrate_*.sql` runs on every
deploy).

**The queue** (`DUE_SQL`): `status = 'ok'`, `method = estimator.METHOD`, `confidence >=
bpm_tag_writeback_min_confidence / 100`, `NOT (tag_bpm <=> bpm)`, the measurement current (its
`file_mtime`/`file_size` equal `library_media_files`' for the track's first file -- the analyzer's own
test), the track's form not in `bpm_analysis_skip_forms`, the file under a root (the EPs tree,
`Soundcloud`, `Youtube`, `Telegram`, `Top 100`), and no path component starting with `.`
(`.quarantine`), `_` (`__TODO`), `#` (`#recycle`) or `@` (`@eaDir`). Newest track first, `LIMIT
bpm_tag_writeback_per_round`. Every outcome except `stale` stamps `tag_bpm = bpm`, so a file is
looked at once per measured value; a re-measurement with another value queues it again. `failed`
and `missing` are stamped too, so a broken file is not retried every round.

## The rule (`decide`)

`target = round_half_up(bpm)`. The file's tag is parsed (`,` as decimal point accepted; empty,
unreadable or outside 40-500 counts as no tag).

| Tag | Outcome |
|---|---|
| none | write (`missing`) |
| within 0.5 BPM of the measurement, or rounds to `target` | leave (`matches`) |
| a whole number *off* the old analyzer's grid, within 1 BPM | leave (`kept`) |
| about double (±2) or half (±1) the measurement | write (`octave`) |
| anything else (the coarse 152/161/172 ... end up here) | write (`differs`) |

The grid is every integer the old analyzer could write: `floor` and `round` of
`60 * 22050 / (512 * n / 2)` for each `n` (143.6, 147.7, 152.0, 156.6, 161.5 ...; see
[bpm-browse technical](../bpm-browse/technical.md)). 150, 155, 160, 175, 200, 210 are off it; near
100 BPM the grid is dense enough that almost every integer is on it, so there the measurement wins.

The confidence threshold defaults to 75, the same as `bpm_reliable_confidence`: on the evaluation
set 89% of the estimates at ≥ 0.75 were right against genuine tags, and where tag and estimator
agree the method is 94.4% within ±1 BPM (84.5% over everything). On production (2026-09-30,
read-only) 144,641 of 245,442 measurements are at ≥ 0.75; 141.6k of those are under the roots.

## Per-format mapping (`write_bpm_tag`)

| Extension | Where | Value |
|---|---|---|
| `.mp3` | ID3v2 `TBPM`, Latin-1; saved in the version the file had (2.3 stays 2.3); a file without ID3v2 gets one. The ID3v1 tag follows mutagen's default (updated only if present), as the tagger's own saves do. | integer text |
| `.wav` | the same frame in the `id3 ` chunk | integer text |
| `.m4a`, `.mp4` | the integer `tmpo` atom (mutagen renders it as a 16-bit integer atom). Never a freeform `----:` atom and never a bare name longer than 4 bytes, which mutagen truncates (services/tagger/constants.py). | integer |
| `.flac`, `.opus`, `.ogg` | Vorbis comment `BPM`, replacing any spelling (`bpm`) | integer text |
| anything else | not written (`unsupported`) | |

Integer because ID3 defines `TBPM` as an integer, `tmpo` is one, and TagLib (LMS) and DJ software
read a whole number everywhere; the precise value stays in the database. Only that one frame/atom
is changed; mutagen writes into the existing padding when it fits (MP3, FLAC) and otherwise rewrites
the tag area. Production's measured files: 179k mp3, 55k m4a, 7.9k flac, 2.3k opus, 950 wav.

## After a write: nothing re-queues it

A write changes the file's mtime and size, which three readers compare. In one transaction
(`BpmTagStore.record_written`), each is moved to the new stat **only if it described the file as it
was just before the write**, so a change nobody had seen yet is never hidden:

- `library_track_bpm.file_mtime/file_size` -- otherwise the analyzer measures the file again.
- `library_media_files.file_mtime/file_size` -- otherwise the scanner re-reads every tag. It reads no
  BPM, so the row still describes the file.
- `tagger_processed_files.mtime`, only when the row is not flagged and not already behind the file
  (`changed_on_disk`), with `last_processed` kept (the column is `ON UPDATE CURRENT_TIMESTAMP`, and
  bumping it would push the deep run's next visit out by a month). Otherwise the daily walk would
  run the whole rule stack on every rewritten file.

A file whose disk stat no longer matches the stored measurement is `stale`: left queued and
unstamped, for the scanner and the analyzer to catch up. LMS is told each written folder
(`lms_scan_trigger.notify`, queued and merged), as the tagger does after a write.

`library_track_audio_features.bpm_tag` is the deprecated ml-analyzer's read of the tag and no longer
changes; `effective.resolve` already prefers the measurement, so no tempo shown anywhere flips.

## Throttle and duration

Settings (Beheer → Config → BPM, read through ConfigStore every round):

| Key | Default | |
|---|---|---|
| `bpm_tag_writeback_enabled` | on | Teun decided yes. |
| `bpm_tag_writeback_paused` | off | |
| `bpm_tag_writeback_per_round` | 300 | 0-5000 files looked at per tagger round. |
| `bpm_tag_writeback_min_confidence` | 75 | 0-100. |

One thread, one file at a time, a pause of `TAGGER_BATCH_PAUSE` (0.5 s) after every 24 writes, and
a stop request (Beheer's stop/restart) honoured between files. The tagger round runs every five
minutes after the previous one ends, so a round with 300 files -- a tag read over CIFS plus, for
most, a small in-place write, estimated 0.1-0.4 s each -- takes 30-120 s and the cadence is about
6-7 minutes: roughly 200-240 rounds, **60,000-70,000 files a day**, so the ~142k files in scope
today (~155k once the analysis finishes) take **two to three days**, after which only new
measurements are written, within a round or two. The per-file cost on production is an estimate;
the round's INFO line (`BPM tags: written N, matches M, ...; R file(s) still to reconcile`) gives
the real rate. Raise the cap to go faster, lower it or pause if the NAS or the API suffers.

## API Contract

No endpoint changes. Four new config keys (above), served by the existing `/api/config`.

## Cross-App Impact

- music-manager: the new step, config keys, three columns.
- LMS: none. It reads the `BPM` property through TagLib (`TagType::BPM`) but stores no tempo and
  its Subsonic `Child` has no `bpm`; exposing it is a follow-up.
- frontend, MuMa Mobile: none.

## Technical Acceptance Criteria

1. `decide` writes on no tag, a coarse or different tag and an octave; leaves a matching tag and a
   genuine off-grid integer within 1 BPM; rounds half up (`test_bpm_tag_writeback.py`).
2. On real mp3 (ID3v2.3 and 2.4), m4a, flac, opus and wav fixtures, only the BPM frame/atom changes:
   every other tag and the audio bytes (MP3 frames after the tag, FLAC frames, the `mdat` payload,
   Ogg audio packets, the WAV `data` chunk) are identical, the ID3 version is kept, m4a gets `tmpo`
   and no freeform twin (`test_bpm_tag_writeback.py`).
3. A round honours off, paused and a cap of 0, passes the cap as the queue limit, stops between
   files, pauses after every slice, notifies LMS once per written folder, stamps every outcome but
   `stale`, and survives unreadable files and a failed bookkeeping write (`test_bpm_tag_writeback.py`).
4. `TaggerManager.run_full` runs the step after the tagger, inside the lock, not after a stop, and a
   failure in it does not end the round (`test_scanner_tagger_routers.py`).
5. On a real MariaDB (`BpmBrowseSqlTest`): the queue returns only confident, current, in-scope
   measurements newest first (not sets, not `__TODO`, `.quarantine`, `#recycle`, Lidarr, not a
   changed file); an outcome takes the file off the queue until its measurement changes; a write
   moves the analyzer's, the scanner's and an up-to-date tagger row to the new stat with
   `last_processed` kept, leaves a flagged tagger row alone, and neither this queue nor the
   analyzer's `DUE_SQL` returns the file afterwards.

## Related Docs

- [bpm-browse](../bpm-browse/technical.md) -- the measurement, the grid, the evaluation.
- [tagger/rescan-paths.md](../tagger/rescan-paths.md) -- the retag queue and why bulk re-queues starve
  the API.
