- The release-date backfill now also picks up tracks that already have a full date from a lower
  rung of the date ladder (an `.nfo` rip date, the arrival date, or the file's own date) when
  their release now offers a better one, such as a Deezer date. Before, only year-only tracks
  were selected, so a track dated from the rip date stayed a day or a week off after its Deezer
  answer came in. The dry run counts these as `upgrade-from-<source>` (and `upgrade-pending`
  while Deezer is not asked yet). A person's date, or one from an equal or better rung, is never
  selected.
- The release-date rule no longer skips a full date without `DATE_SOURCE` that equals the
  release's `.nfo` date or the file's own `DATE`. Those dates were written by the same rule before
  the date ladder existed, and were taken for a person's date: the first backfill round on
  production left 4.141 of 15.385 files unchanged for that reason, some of them days off the
  Deezer date. Such a date now counts as its source, so a better source replaces it, and
  otherwise it gets its `DATE_SOURCE`.
