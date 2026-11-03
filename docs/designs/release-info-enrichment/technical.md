# Release Info Enrichment — Technical Design

Implements [`functional.md`](functional.md). Builds on bug report 145 (the catalogue-number test the
Renamer and this feature share) and on the importer and tagger as they are: the Mover's
proposal flow (`docs/designs/todo-label-backlog/`), `InferReleaseDateFromNfoRule`, the tagger
queue, and the release-date sync that copies LMS's dates into muma.

## Modules

| Module | Role |
|---|---|
| `services/common/catalogue_number.py` | `is_catalogue_number`, `rejection`, `from_folder_name`, `old_rule_prefix` (bug report 145). |
| `services/common/release_nfo.py` | Pure .nfo reader: `parse(text) -> NfoInfo(label, label_key, catalogue_number, links)`, `read(dir)`, `decode(bytes)` (CP437, NULs dropped). Two-column `Key....: value` pairs; label keys `label, recordlabel, labelname, company, publisher` in that order; catalogue keys `catalognr, catalognumber, catalogno, catalog, catno, catnr, catalogue, catalogueno`, accepted by `nfo_catalogue_number` (the folder-name rule plus "holds a letter", so a UPC never passes); album links for Deezer, Beatport, Qobuz, Tidal. |
| `services/common/store_lookup.py` | `fetch_deezer(album_id)`, `StoreCache.lookup(link, budget=None)`, `Budget`. One process-wide 0.25 s request slot; quota (HTTP 429 or error code 4) raises `StoreThrottled`, which ends the caller's budget for the cycle; error 800/HTTP 404 is `not_found`; anything else transient returns None and is not stored. Without a `Budget` nothing goes over the network. A per-process LRU (4.096 albums) sits in front of the table. |
| `services/importer/label_match.py` | `fold(name)` and `LabelIndex`: existing label folders (via `ImportQueue.is_label_folder`, so neither the queue nor `__Free&None`) by folded name, plus confirmed proposals (`proposed_label -> decided_label`) as aliases. A key with two folders matches nothing. |
| `services/importer/release_info.py` | `ReleaseInfo`: .nfo facts per folder cached against the .nfo's (path, size, mtime); `catalogue_number`, `album(budget)`, `placement(index, budget) -> Placement(label, source, stated)`. |
| `services/tagger/Song/rules/InferReleaseDateFromNfoRule.py` | The date ladder (below). |
| `services/tagger/release_date_backfill.py` | Dry-run backfill CLI; `backfill-release-dates.sh` wraps it. |

## Data Model

New table, `services/common/db_init.py` and `migrate_v55_release_store_lookups.sql` (same shape,
expand-only, re-runnable):

```sql
CREATE TABLE IF NOT EXISTS release_store_lookups (
    store VARCHAR(16) NOT NULL,          -- 'deezer'
    album_id VARCHAR(64) NOT NULL,
    status ENUM('ok', 'not_found') NOT NULL,
    label VARCHAR(255) NULL,
    upc VARCHAR(32) NULL,
    release_date VARCHAR(10) NULL,       -- as the store gives it
    title VARCHAR(255) NULL,
    fetched_at DATETIME NOT NULL,        -- UTC
    PRIMARY KEY (store, album_id)
);
```

`not_found` rows are asked again after 30 days.

The owner's decision on #164 adds, in `migrate_v56_label_name_choices.sql` (same shape in
`db_init.py`, expand-only):

```sql
CREATE TABLE IF NOT EXISTS rules_label_name_choices (
    nfo_label_key VARCHAR(191) NOT NULL PRIMARY KEY,   -- label_match.fold(.nfo label)
    nfo_label VARCHAR(255) NOT NULL,
    name_folder VARCHAR(255) NOT NULL,                 -- the folder the name maps to
    history_folder VARCHAR(255) NOT NULL,              -- where the curator filed most such releases
    history_count INT NOT NULL DEFAULT 0,
    name_count INT NOT NULL DEFAULT 0,
    examples TEXT NULL,
    chosen_folder VARCHAR(255) NULL,                   -- his answer; never touched by a re-learn
    decided_at TIMESTAMP NULL,
    learned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE rules_label_proposals ADD COLUMN IF NOT EXISTS alternative_label VARCHAR(255) NULL;
ALTER TABLE rules_label_proposals ADD COLUMN IF NOT EXISTS label_choice_key VARCHAR(191) NULL;
```

Seeded with the 104 pairs measured on 2026-10-02 (`INSERT IGNORE`); re-learned by
`python -m services.importer.label_history [--apply]`. `rules_label_proposals` is also read for
`created_at` (arrival) and for confirmed aliases.

New tags (`services/tagger/constants.py`, registered in `tag_registration.CUSTOM_TAG_KEYS`):

| Name | MP3 | FLAC/Opus | WAV | m4a |
|---|---|---|---|---|
| `DATE_SOURCE` | `TXXX:DATE_SOURCE` | `DATE_SOURCE` | `TXXX:DATE_SOURCE` | freeform `DATE_SOURCE` |
| `BARCODE` | `TXXX:BARCODE` (EasyID3's own `barcode`) | `BARCODE` | `TXXX:BARCODE` | freeform `BARCODE` |

The release date itself goes where the tagger already puts a resolved release date: ORIGINALDATE
(`TDOR` on MP3). LMS reads it into `track.original_date`, sorts "recent" on
`COALESCE(t.original_date, t.date)`, and the release-date sync copies
`COALESCE(NULLIF(original_date, ''), date)` into `library_tracks.release_date`. DATE stays the
file's own value, as the tagger has always kept it. No second sync is built: the existing chain
(tag -> LMS scan -> release-date sync) carries the new date everywhere.

## Configuration

ConfigStore group `Importer`, rendered by Management > Configuration without frontend changes:

| Key | Default | Effect |
|---|---|---|
| `import_place_by_label_name` | `true` | Mover places a release no rule routes by .nfo/Deezer label. |
| `import_store_lookups` | `true` | Importer may ask Deezer. Off: no request leaves the process. |
| `import_store_lookups_per_cycle` | `60` | New Deezer requests per import cycle (~15 s at four a second). |
| `import_label_name_moves_per_cycle` | `50` | Releases placed by label name per cycle; the rest wait a cycle. |

## Flow

**Renamer** (`find_cat_id(folder) or self._from_nfo(folder)`): a name without a catalogue number
gets the .nfo's, if any; otherwise the folder keeps its name and the settle walk is skipped.

**Mover**, per settled folder, in this order:

1. `get_cat_id` + `rules_catid_label` -> move, unchanged.
2. Else `_place`: if `import_place_by_label_name`, `ReleaseInfo.placement`:
   - the `.nfo` label has a `rules_label_name_choices` row with `chosen_folder` (an existing folder)
     -> placed there;
   - it has a row without a choice -> `Ask(name_folder, history_folder)`: the Mover records a
     proposal `proposed_label=name_folder, alternative_label=history_folder,
     label_choice_key=<key>, source='nfo-vs-history'` (fingerprinted under its own key, so it is
     written once) and moves nothing;
   - otherwise the `.nfo` label mapped through `LabelIndex`; the Deezer album's label (looked up
     within the cycle's budget) as fallback; both mapped to different folders -> None.
   A placement counts against the cycle's move cap; an `Ask` does not.
   A placement goes through the same `_move_to_label` as a rule move (conflict checks, chmod, LMS
   notify, tagging).
3. Else `_propose` (unchanged, fingerprint-skipped). `label_resolver` now reads the .nfo through
   `release_nfo`, so a `Company` line becomes the proposed label.

`_move_to_label` additionally, before the move: warms the store cache for the release
(`ReleaseInfo.album(src, budget)`), takes the arrival date (`rules_label_proposals.created_at` of
the folder's row, else today), and decides the push: a folder with a proposal row is backlog and
gets `push=False`. `post_processing_songs(dst, arrival_date=...)` sets `song.arrival_date` before
`LabelSong.parse()`.

The importer service hands the Renamer's `ReleaseInfo` to the Mover, so one .nfo read serves both.

## The date ladder (`InferReleaseDateFromNfoRule`)

Ranks (lower wins): `deezer` 10, `nfo-street`/`nfo-release` 20, `tag` 25, `nfo-rip` 30,
`arrival` 40. `expected_year` = the year in the release directory's name, else DATE's year.

1. `deezer`: the .nfo's Deezer link -> `StoreCache.lookup(link)` without a budget (cache only)
   -> `full_date` whose year is `expected_year`.
2. `nfo-*`: `NfoDate.resolve` (unchanged, now also reading `Store date`/`Retail date` as release
   dates) -> its kind.
3. `tag`: DATE at day precision, year guarded.
4. `arrival`: `song.arrival_date` when its year is `expected_year`.

Write rule: current ORIGINALDATE at day precision without a known DATE_SOURCE -> `infer_source`:
when it equals the `.nfo` date or the full DATE (what this rule wrote before the ladder, without a
source), it counts as that rung, and gets DATE_SOURCE stamped even when nothing better exists.
Any other such date -> leave alone.
Otherwise write `(date, source)` when there is no day-precision date yet, when the rank is
strictly better, or when the same source now gives a different date. BARCODE := album UPC when
the file has none.

## Backfill

`python -m services.tagger.release_date_backfill [--lookup N] [--apply]`, in music-manager.
Candidates: `library_media_files` under `eps_folder_path` whose track's `release_date` is '' or
NULL, the import queue left out (`ImportQueue.contains`). Grouped per directory and judged like
the rule (`deezer`, `deezer-pending`, `deezer-gone`, `nfo-*`, `none`). `--lookup` fills the cache
within a `Budget(N)` and writes only `release_store_lookups`; `--apply` upserts
`tagger_processed_files(needs_rescan=TRUE, rescan_reason='release_date_ladder')` for the
`deezer`/`nfo-*` tracks. The tagger's rounds write the tags.

A track with a full `release_date` is a candidate as well when its file's DATE_SOURCE ranks
below the best rung its directory offers now (`SOURCE_RANKS`). Only directories with a Deezer
link or an `.nfo` date are looked at. A track whose date already equals the best date is skipped
without a read; the others get one mutagen read for DATE_SOURCE (`TXXX:DATE_SOURCE`, Vorbis
`date_source`, MP4 `----:com.apple.iTunes:date_source`). Verdicts: `upgrade-from-<source>`
(queued by `--apply`) and `upgrade-pending` (Deezer not asked yet; `--lookup` asks for these
albums first, before the year-only ones). No DATE_SOURCE, or an equal or better one, is never a
candidate, the same guard as the rule's write rule. The report adds `dated_tracks` and
`upgrade_tracks`.

## API Contract

Additive only, no breaking change.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/label-proposals` | unchanged | each row also carries `alternative_label` and `label_choice_key` (null for ordinary proposals) | unchanged |
| `POST /api/label-proposals/{id}/confirm` | unchanged (`{"label": ...}`) | unchanged | unchanged; when the row has `label_choice_key`, the same transaction sets `rules_label_name_choices.chosen_folder` to the confirmed label |

The web UI (Management > Label proposals) groups a two-option proposal apart from plain proposals for
the same label and shows both folders as buttons; it is the only consumer.

## Cross-App Impact

`services/frontend` (label proposals tab) changes with the API in the same MR. LMS, the web player and the app read ORIGINALDATE as they already do; the
new tags are informational. `GET /api/config/fields` lists four new fields in group `Importer`.

## Technical Acceptance Criteria

1. `release_nfo.parse` reads `Company.: B2S` and `Url:https://deezer.com/album/1104265012` from the
   two-column UTNG layout; a UPC is never a catalogue number (`release_nfoTest`).
2. `StoreCache.lookup` without a budget never calls the network; a quota answer ends the budget;
   a network failure stores nothing; `not_found` is re-asked after 30 days (`store_lookupTest`).
3. `LabelIndex.match('b2s Records') == 'B2S'`; a name folding onto two folders matches nothing;
   the queue and `__` folders are never labels (`test_importer_label_match`).
4. The Mover places Minus Militia under `EPs/B2S` with `Label from: nfo:company (B2S)`, warms the
   Deezer cache first, pushes once for a new release and not for a backlog one, respects both
   switches and the per-cycle cap, and still lets a catalogue rule win (`test_importer_release_info`).
5. The ladder writes `2026-10-02`/`deezer` and BARCODE with a cached album, `2026-10-01`/`nfo-rip`
   without, upgrades `nfo-rip` to `deezer`, never downgrades, never touches an unknown full date,
   treats an unsourced full date equal to the `.nfo` date or DATE as that rung,
   uses `arrival` only within the year (`InferReleaseDateFromNfoRuleTest`).
6. The backfill dry run writes nothing and asks nobody; `--lookup` and `--apply` touch only their
   one table each; a full-date track on a lower rung is counted as `upgrade-from-<source>` and
   queued, and a track without DATE_SOURCE or on an equal or better rung never is
   (`ReleaseDateBackfillTest`).
7. `test_schema_drift` passes: `db_init.py` and `migrate_v55`/`v56` build the same tables.
8. An undecided name-versus-filing pair is proposed with both folders and nothing moves; a decided
   one places in the chosen folder; confirming a two-option proposal stores the choice in the same
   transaction (`test_importer_release_info`, `test_management_router`, `test_router_sql`);
   `label_history.learn` builds the pairs and never writes `chosen_folder`
   (`test_importer_label_history`).

## Related Docs

- [Bug report 145](../../bug-reports/145-renamer-takes-festival-anthem-for-catalogue-number.md)
- [Importer design](../importer/technical.md), [`__TODO` label backlog](../todo-label-backlog/technical.md)
