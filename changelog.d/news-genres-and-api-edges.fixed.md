- **News recorder.** A capture that failed part way left its `.part` file behind; deleting a source
  left its recordings on disk; a retention of 0 deleted the bulletin just recorded and a negative
  one captured the same hour twice; two record-now presses in the same minute shared one file and
  got two rows; and a second source due at the same hour waited for the first, while each capture
  held a database connection for its full ten minutes. Recordings are now named to the second, one
  source records one capture at a time (record-now answers 409 while it does), sources due together
  are captured side by side, no connection is held during a capture, and out-of-range source
  settings are a 422. A `Range` such as `bytes=10-5` is a 416 instead of a negative
  `Content-Length`.
- **ListenBrainz import stopped at 10.000 listens and said `completed`.** It now ends as
  `truncated` at its page cap and the next import for the same account continues below the oldest
  listen reached (`scrobble_imports.oldest_listened_ts`, `migrate_v35`). Paging no longer skips the
  listens that share the boundary second (`max_ts` is exclusive already), and a listen without a
  timestamp no longer fails the whole import with a `TypeError`.
- **`GET /api/library/tracks` and `/advanced`: page 0 was a 500 and `limit` had no ceiling.** Both
  now answer 422 for `page < 1` or `limit > 500`. `/tracks` also dropped `sc_url`/`yt_url`, two
  correlated `LIKE '%…%'` scans of the download archives per row that no client read.
- **Logging in with a non-ASCII password, or one over bcrypt's 72-byte limit, was a 500** that the
  login rate limiter never counted. Both are now an ordinary 401.

<!-- release notes -->
- News recordings no longer leave stray files behind, and a second news source is recorded at the
  same time as the first instead of ten minutes later.
- A long ListenBrainz history is imported completely over successive runs instead of stopping at
  10.000 listens.
