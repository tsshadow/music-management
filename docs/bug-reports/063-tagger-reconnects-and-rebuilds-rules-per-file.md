# Tagger Opened Three To Six Database Connections And Rebuilt Its Rule Stack For Every File

# status: fixed

# reported problem
Found while reading the code for the September 2026 audit (item C7), not from a symptom: the
tagger spent far more per file than the tag write itself, and all of it on the thread that shares
the GIL with the music-manager API.

- **A fresh pymysql connection per helper call.** Every helper on the per-file path went through
  `DatabaseConnector.connect()`, which opens a new socket each time: `needs_processing` (the pending
  pass has no snapshot), `download_info.stored_info`, `ingestion.record`, `mark_processed`, and on a
  SoundCloud/Telegram/YouTube file two more for the ignore and genre lists (below), plus one per
  unknown genre in `GenreRulesHelper.record_unknown`. `ProcessedFilesHelper.load_snapshot` measured
  a connect on production at ~14 ms against 0.1 ms for the query, so three to six connects is
  roughly 40-85 ms of every file.
- **The whole rule stack per file.** Every Song subclass built its rule list inside `parse()`.
  `InferArtistFromTitleRule` turned the ~37k-row artist snapshot into a set twice (once for itself,
  once for its "presents" sub-rule) and called `FilterTableHelper.get_all()` on the ignore list and
  on the genre list -- which is not cached, so two database round trips on fresh connections. The
  construction alone measured 12.9 ms of CPU per file locally over 37k synthetic names, with the
  GIL held.
- **`scan_single` reloaded the genre rules before it tried the lock.** While a full scan held the
  scanner lock, every single-file scan ran the reload query and then gave up after
  `SINGLE_SCAN_LOCK_TIMEOUT`, throwing the result away.
- Nothing measured any of this after a deploy: a round logged how many files the pending pass
  handed out, not what they cost.

# Possible reason
The helpers were written for one-off callers (the downloader, the importer, an API request),
where a connection per call is the simple and correct choice, and the tagger reused them in a
loop. The snapshot work of bug report 051 and the 0.66.1 artist cache removed the biggest costs
(the per-file `needs_processing` query in the walk, the 57k-row artist read per file) but kept the
shape: each helper still connected for itself, and each song still assembled its own rules.

# solution
- `services/common/Helpers/RoundScope.py`: inside `round_scope()`, `DatabaseConnector.connect()`
  lends the calling thread the one connection it holds for the round. A helper's `close()` ends the
  transaction (a rollback -- what closing the socket did to anything uncommitted, and what keeps the
  next helper off a stale REPEATABLE READ snapshot) instead of the socket. A pymysql connection is
  not thread-safe, so the connection belongs to its thread: worker threads join the round through
  the thread pool's initializer, and threads that never joined (the event writer, uvicorn's) keep
  getting fresh connections. A helper that connects while its thread's connection is still lent out
  gets a separate real one, a connection whose rollback fails is replaced, and one idle for 30 s is
  pinged first. The round closes all of them when it ends. Outside a round nothing changed.
- `Tagger.run` is the round. It keeps one `ThreadPoolExecutor` for the whole round instead of one
  per slice (a thread that exits would take its connection with it); the slice-then-pause rhythm
  that keeps the API responsive is unchanged, and a stop request still cancels what was not started
  and waits for what was.
- `services/tagger/Song/rule_stack.py` builds each song type's rules once per round and hands the
  same rule objects to every file and worker; outside a round (`TagSingleFile`, downloader,
  importer) a fresh list, as before. The rules hold no per-file state. `InferArtistFromTitleRule`
  follows the `library_artists` snapshot identity and rebuilds its name sets only when the helper
  publishes a new one (once a minute, or when an artist is added), so a round-long rule sees the
  same names a per-file rule did. The ignore and genre lists are read once per round, at the same
  point everything else a round depends on is refreshed.
- `ScannerManager.scan_single` takes the lock first and reloads the rules under it.
- One summary line per round: `Tagging round: N file(s) tagged (W written, S up to date) in Xs,
  M ms/file, C database connection(s) opened` -- `INFO` when anything was tagged, `DEBUG` for an
  idle round so the five-minute loop does not add an event row for nothing.

What can differ from before: a genre that `record_unknown` registers mid-round no longer joins the
"not an artist" genre list of `InferArtistFromTitleRule` until the next round, and a name put on the
ignore list mid-round waits for the next round too. Both were already order-dependent under twelve
parallel workers, and every other rule cache is refreshed per round in the same way.

Tests: `services/common/Helpers/RoundScopeTest.py`, `services/tagger/TaggerRoundTest.py`,
`services/tagger/Song/RuleStackTest.py`, and two cases in
`services/music_manager/tests/test_scanner_tagger_routers.py`.
