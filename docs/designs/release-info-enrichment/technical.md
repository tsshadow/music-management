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
| `services/tagger/release_date_backfill.py` | Dry-run backfill CLI; `scripts/prod/person/backfill-release-dates.sh` wraps it. |

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

`not_found` rows are asked again after 30 days. No other table changes; `rules_label_proposals`
is read for `created_at` (arrival) and for confirmed aliases.

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

ConfigStore group `Importer`, rendered by Beheer > Configuratie without frontend changes:

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
2. Else `_place`: if `import_place_by_label_name` and moves are left this cycle,
   `ReleaseInfo.placement` -> `.nfo` label mapped through `LabelIndex`; the Deezer album's label
   (looked up within the cycle's budget) as fallback; both mapped to different folders -> None.
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

Write rule: current ORIGINALDATE at day precision without a known DATE_SOURCE -> leave alone.
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

## API Contract

No endpoint changes.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| — | — | — | — |

## Cross-App Impact

None at the API level. LMS, the web player and the app read ORIGINALDATE as they already do; the
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
   uses `arrival` only within the year (`InferReleaseDateFromNfoRuleTest`).
6. The backfill dry run writes nothing and asks nobody; `--lookup` and `--apply` touch only their
   one table each (`ReleaseDateBackfillTest`).
7. `test_schema_drift` passes: `db_init.py` and `migrate_v55` build the same table.

## Related Docs

- [Bug report 145](../../bug-reports/145-renamer-takes-festival-anthem-for-catalogue-number.md)
- [Importer design](../importer/technical.md), [`__TODO` label backlog](../todo-label-backlog/technical.md)
