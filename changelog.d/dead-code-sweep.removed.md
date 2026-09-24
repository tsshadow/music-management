- **Dead code removed.** `services/other/` (an artist fixer, converter, EPs flattener that
  duplicated `services/importer/flattener.py`, file repair, sanitizer and an unimportable
  `yt-fixer.py`, 461 lines that only their own tests imported) and its tests;
  `services/tagger/run_tagger.py`; `VerifyArtistRule`, reachable only through `services/other`;
  seven one-off tools (`check_media`, `finalize_genres`, `init_remote_db`, `list_imports`,
  `replace_table_names`, `repro_mutagen`, `migrate_db_renames`); the frontend's Vite template
  leftovers (`Counter.svelte`, `hero.png`, `svelte.svg`, `vite.svg`); the unused
  `subsonic/VideoPlayer.kt`; and an empty `ultrasonic-database.db` committed into the Android tree.
- **The `/api/jobs` registry and its WebSocket are gone.** Nothing read them: the downloader and
  importer side only pushed when `HUB_API_URL` was set, which no deployment did, and the WebSocket
  took no key. The curation pages' own job progress (artist and genre analysis, a rule's retag) now
  lives in `services/music_manager/job_store.py`, which keeps the last 50 finished jobs instead of
  every job for the life of the process.
