# Scanner Failed m4a Files With "Data too long for column 'title'" On Every Pass

# status: fixed

# reported problem
GitLab issue #91. Production event log, 2026-09-26 12:00 to 2026-09-27 00:35: 280 `ERROR` rows
from `music-manager.scanner` reading
`Error processing <path>.m4a: (1406, "Data too long for column 'title' at row 1")` -- 160 on
`title`, 120 on `display_artist`. 28 files, every one of them 10 times in those 12 hours, among
them `Youtube/Q-dance/The Sound of Q-dance Chile ｜ Official Q-dance Aftermovie.m4a`,
`Youtube/101Barz/#TBT - The Opposites ｜ Throwback Sessie ｜ 101Barz.m4a`,
`Soundcloud/Crypton/Crypton - Until It's Gone.m4a` and five `Soundcloud/BadAss Events/` sets. The
visible titles are short, and both columns are `VARCHAR(512)`.

# Possible reason
Not the fullwidth `｜`: MariaDB counts `VARCHAR` length in characters, not bytes. Not a wrong atom
either. Read-only mutagen inspection of the files on production showed the tags really are that
long -- one value repeated over and over, joined by `;`:

| File | Tag | Length | Content |
|---|---|---|---|
| `Crypton - UNTIL IT'S GONE.m4a` | `©nam` (title) | 3,863 | `UNTIL IT'S GONE` x241, `Crypton` x1 |
| | `ORIGINAL_TITLE` | 3,881 | `UNTIL IT'S GONE` x241, `Crypton - UNTIL IT'S GONE` x1 |
| `Unexist @ Karma Outdoor 2025.m4a` | `ORIGINAL_ARTIST` (display artist) | 3,427 | `Karma Outdoor 2025` x181 |
| `The Sound of Q-dance Chile ｜ ...Aftermovie.m4a` | `©nam` | 3,834 | `Official Q-dance Aftermovie` x137 |

How they grew: before 0.72.2 (bug report 037) the tagger wrote ORIGINAL_TITLE to a bare
`ORIGINAL_TITLE` key. mutagen writes a bare m4a atom name as exactly four bytes, `ORIG`, so the
value never read back under its own name -- and on the next save the tags held both the `ORIG`
that had been read and a new `ORIGINAL_TITLE`, which mutagen wrote as a second `ORIG` atom.
mutagen merges same-named atoms into one list on read. One more copy per retag, and the title the
artist rules derive from ORIGINAL_TITLE grew along with it. Reproduced with real mutagen in
`tests/unit/test_tagger_idempotence.py`. 0.72.2 stopped the growth (freeform atoms, legacy
`ORIG` read once and removed) but migrated the accumulated copies into the new atom as they were.

Why it repeated: a file whose write fails gets no `library_media_files` row, so `_is_up_to_date`
never holds and every full scan reads it again. The scanner had no failure count of its own.

The same damage, short enough to fit, sits on more files: 1,900 `library_tracks.title` values on
production have identical second and third `;`-separated segments.

# solution
- **The scanner stores the file anyway.** `process_file` cuts a title, display artist, artist name
  or label name longer than its column to the column's character length (`fit_column`; a Python
  slice counts code points, as MariaDB does under utf8mb4, so no character is split), logs one
  `WARNING` naming what was cut, and queues the file for the tagger with reason `overlong_tag`.
- **The tagger repairs the tags.** New `CollapseRepeatedValuesRule`, first in every song's rule
  list: when ORIGINAL_TITLE, TITLE or ORIGINAL_ARTIST holds a value more than once -- the defect's
  signature; a title that legitimately contains `;` splits into distinct values and is left alone
  -- ORIGINAL_TITLE keeps its longest value (the downloaded title, of which every derived value is
  a part) and TITLE/ORIGINAL_ARTIST their most frequent one. The artist rules then re-derive the
  title from the repaired original. The tagger's write changes the file's mtime, so the next scan
  indexes the short value. The 1,900 shorter cases are repaired as the tagger's deep run (every file once per
  `tagger_deep_run_days`, 30 by default) reaches them; nothing is queued in bulk.
- **A file that keeps failing is parked.** `_process_file_safe` counts failures per path and
  (mtime, size); after `SCANNER_PARK_AFTER` (3) in a row it logs one `WARNING` and skips the file
  until it changes or the service restarts (the count is in memory: a deploy, which is when a fix
  arrives, gives each parked file one more try). A forced scan ignores the parking.
- Tests: `services/music_manager/tests/test_scanner_overlong.py`,
  `services/tagger/Song/rules/CollapseRepeatedValuesRuleTest.py`,
  `tests/unit/test_tagger_idempotence.py` (real mutagen: the growth, and a retag that repairs
  and then writes nothing). No SQL statement changed, so the integration suite needed no case.
