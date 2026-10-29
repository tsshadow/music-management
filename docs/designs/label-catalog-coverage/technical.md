# Label Catalogue Coverage — Technical Design

Implements [`functional.md`](functional.md).

## Data Model

No schema change. There is no catalogue-number column anywhere; the number lives only in the
release folder name, which `library_media_files.file_path` carries in full:

```
<eps_folder_path>/<label>/<CATID rest-of-release-name>/<file>
```

The endpoint reads

- `library_labels(id, name)` — the label, by name (UNIQUE);
- `library_track_labels(track_id, label_id)` — which tracks carry it;
- `library_media_files(file_path, track_id)` — the files behind those tracks.

`rules_catid_label` is **not** consulted: the series prefix comes out of the parsed catalogue numbers
themselves, and the table contains junk rows (`_`) and prefixes that do not map one-to-one to a
series on disk.

### Path → catalogue number

`services/tagger/Song/LabelPath.split(path, eps_root, delimiter)` is reused as-is: it anchors on
the EPs root (`ConfigStore().eps_folder_path`, the same setting the tagger and the importer read) so
a scene release that nests a second copy of its folder still yields the right release folder, and
falls back to the two folders above the file for a path outside the root.
`LabelPath.catalog_number(release_folder)` takes the first space-separated token. A file whose
release folder is empty (it sits directly in the label folder) is skipped.

### Catalogue number → (prefix, number, suffix)

New pure module `services/music_manager/catalog_series.py` (strictly type-checked; it is new code).

```
^(?P<prefix>.*?)(?:[-_](?P<sep_number>\d+)|(?P<number>\d{3,}))(?P<suffix>\D*)$
```

- The lazy prefix and the `\D*$` suffix together make the number the **last** run of digits in the
  string, so `247HC001` → (`247HC`, `001`, ``) and `AFT3R001` → (`AFT3R`, `001`, ``).
- A run needs at least three digits **unless** a `-`/`_` separates it from the prefix; that is what
  admits `R909-29` (series `R909`, number `29`) and `DWXCD-050` (series `DWXCD`, number `050`) while
  keeping `AFT3R` from being split at its `3`. The separator is dropped from the prefix.
- A non-empty suffix (`DWX1105D`, `DWX0544-`, `DWX2149EPD`) is a **variant**: the number fills its
  position but the catid is also reported.
- An empty prefix is allowed (`000`, `001` — Black Reaper Records numbers its releases bare).
- Anything that does not match (`DWXFREE`, `01`, `Act`) is **other**.
- The series key is the prefix upper-cased; the prefix as shown is that same upper-cased form.

### Per series

For each series, over its distinct catids (compared upper-cased):

| Field | Meaning |
|---|---|
| `prefix` | Upper-cased prefix, `''` for bare numbers |
| `separator` | The separator seen most often between prefix and number (`''`, `-` or `_`), so the UI writes `R909-30` and `DWX0177` |
| `min`, `max` | Lowest and highest number held |
| `width` | Most common digit-string length; ties go to the wider one so the newest releases are never truncated when padding |
| `present` | Distinct numbers held (a plain catid and its variant count once) |
| `releases` | Distinct catids in the series, variants included |
| `absent_count` | `(max − min + 1) − present` |
| `absent` | The absent numbers, ascending; `[]` when truncated |
| `absent_runs` | `absent` compressed to `[[from, to], …]`; `[]` when truncated |
| `absent_truncated` | `true` when `max − min + 1 > 20000` (`EXPANSION_CAP`) — one malformed outlier must not produce a 2-million-entry response |
| `coverage` | `present / (max − min + 1)`, rounded to three decimals |
| `variants` | `[{catid, release_folder}]`, sorted by catid |

Series are sorted by `present` descending, then prefix.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/curation/labels/{name}/catalog` | Path: label name (URL-encoded). Auth: `music.read`, same as `GET /labels/{name}`. | `{ name, files_considered, files_outside_root, series: [Series…], other: [{catid, release_folder}] }` — `files_considered` is the number of distinct files read, `files_outside_root` how many of those were skipped for not being under the EPs root; `other` is sorted by catid. | `401`/`403` per the shared auth dependency; `404 Unknown label` when the name is not in `library_labels`. |

Computed on demand from two queries, merged by path:

```sql
-- 1. what the scanner linked to the label
SELECT mf.file_path
FROM library_track_labels tl
JOIN library_media_files mf ON mf.track_id = tl.track_id
WHERE tl.label_id = %s;

-- 2. what sits in the label's folder on disk
SELECT mf.file_path FROM library_media_files mf WHERE mf.file_path LIKE %s;   -- '<eps_root>/<label name>/%'
```

**Why both.** The label link is what the scanner wrote, and it lags the disk: on production
`library_track_labels` links 2 706 files to Dirty Workz while 5 531 files sit under
`/mnt/music/EPs/Dirty Workz/` — roughly half the EPs tree has no link yet after a skipped rescan
(see `eps_label_gap_is_a_skipped_rescan`). The page's whole point is what is *on disk*, so the
folder is read by path as well. The join is kept for files whose folder is named differently from
the label (a sublabel folder, a moved release). The LIKE prefix is the label's stored name with `%`,
`_` and `\` escaped (`_like_prefix`), so `__Free&None` does not also match `xxFree&None`; the path
query is skipped when no `eps_folder_path` is configured. The union is deduplicated by path before
`catalog_series.build_catalog(paths, eps_root, delimiter)` runs.

**Only the EPs tree is read.** The join also brings in the label's files under `Soundcloud/`,
`Podcasts/`, `Top 100/` and `Top-100/` (74 + 44 + 20 + 33 for Dirty Workz). There the folder above
the file is a channel or a show, and `LabelPath.split`'s fallback would hand it over as a "release
folder": a channel named after the label lands in `other`, a show named `Set 2019` becomes a bogus
series. So when `eps_root` is set, `build_catalog` skips every path not under it and reports how
many in `files_outside_root`; the two-folders-above-the-file fallback survives only for the case
that no root is configured at all.

A label with no files answers `200` with an empty `series` and `other` — that is the page's empty
state, not an error. No breaking change: the existing label endpoints are untouched.

## Cross-App Impact

- `music-manager`: new route in `routers/curation.py`, new module `catalog_series.py`.
- `frontend`: `curationApi.loadLabelCatalog(name)`, a new `LabelCatalog.svelte` section rendered
  by `LabelEdit.svelte`, and the pure formatter `catalogRuns.js` (run formatting, padding, the
  clipboard text). Literal Dutch strings, as the rest of the curation pages.
- LMS proxy and MuMa Mobile: none. The route sits under `/api/curation/`, which is already routed
  to MuMa directly.

## Technical Acceptance Criteria

1. `parse_catid`: `DWX0001` → (`DWX`, 1, `0001`, ``); `DWX1105D` → suffix `D`; `DWX0544-` → suffix
   `-`; `DWXCD-050` → (`DWXCD`, 50); `247HC001` → (`247HC`, 1); `R909-29` → (`R909`, 29); `AFT3R001`
   → (`AFT3R`, 1); `001` → (``, 1); `DWXFREE`, `01`, `Act`, `` → `None`.
2. Series grouping is case-insensitive: `dwx001` and `DWX002` are one series with prefix `DWX`.
3. `DWX000` and `DWX0999` together give width 4, min 0, max 999, present 2, `absent_count` 998,
   first run `[1, 998]`.
4. A variant fills its position: `DWX1105D` alone gives present 1 and one variant; `DWX1105` plus
   `DWX1105D` gives present 1, releases 2.
5. Runs: absent `[1, 2, 3, 7, 10, 11]` → `[[1, 3], [7, 7], [10, 11]]`.
6. A series spanning more than 20 000 numbers returns `absent_truncated: true`, empty `absent` and
   `absent_runs`, and the correct `absent_count`.
7. `other` entries never affect any series' `min`/`max`.
8. `files_considered` counts every distinct file read, including files whose release folder is
   empty; a file outside the EPs root is skipped, counted in `files_outside_root`, and never lands
   in a series or in `other`. With an empty `eps_root` the two folders above the file are used.
9. Series order: most `present` first.
10. `GET /api/curation/labels/{name}/catalog` returns 404 for an unknown label, 200 with the
    computed body for a known one, and is listed in `tests/integration/test_router_sql.py` so its SQL
    runs against a real schema in CI. A file under `<eps_root>/<label>/` with no row in
    `library_track_labels` is counted (router unit test and integration test); a file in both
    queries is counted once; the LIKE parameter is the escaped label folder plus `%`.
11. Frontend: `formatRuns` renders `[[287, 289]]` with prefix `DWX`, width 4 as `DWX0287–DWX0289`
    and `[[177, 177]]` as `DWX0177`; `searchTerms` expands `[[287, 289]]` to three lines.
12. Frontend: the section shows the header, the runs, the variants and the other list from a mocked
    response; shows the empty state for an empty response; shows its own error on a failed fetch; the
    copy button writes the expanded list to `navigator.clipboard`.

## Related Docs

- [`docs/designs/importer/`](../importer/) — where the release-folder layout comes from.
- [`services/tagger/Song/LabelPath.py`](../../../services/tagger/Song/LabelPath.py) — the path split reused here.
- [`../genre-curation/technical.md`](../genre-curation/technical.md) — the curation edit pages this extends.
