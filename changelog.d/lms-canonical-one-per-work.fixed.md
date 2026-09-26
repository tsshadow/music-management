- **Every song now has exactly one canonical row in LMS.** The song-version push marked canonical
  per file, so a canonical track with several files (the FLAC and the MP3 of one release) put every
  file in canonical-only lists -- 5,226 works were shown more than once -- and a work whose
  canonical file LMS does not have got no canonical row at all, so 1,081 songs vanished from
  canonical-only lists in the app and Android Auto. The push now decides per work: the canonical
  track's best file (the scanner's own media row, then format and bitrate, then the newest) is the
  only canonical row, and when LMS lacks that track the best version LMS does have stands in
  (counted in the hourly log). It reuses bug report 093's one-row-per-path rule and compares before
  writing, so an unchanged run writes nothing. Bug report 097.

<!-- release notes -->

- **Songs no longer show up twice, or go missing, in the player's lists when only the preferred
  version is shown.**
