- **A file the tagger could not read was retried every five minutes, forever, with an alert each
  time.** A failed file kept its place on the retag queue, was handed out again on the next round and
  logged another `ERROR` — and every `ERROR` is an event and an alert push. Failures now back off
  (10, 20, 40, 80 minutes) and the fifth in a row parks the file with reason `failed` until it changes
  on disk or a retag is requested: one `WARNING` for the first failure, one for the park, `INFO` in
  between, no `ERROR`. `GET /api/tagger/retag/pending` reports the parked files as `failed`, outside
  `total`, and the tagger page shows the count. New columns `attempts`/`last_attempt` (migrate_v37).
  Bug report 051.
- **Two files whose paths differed only in case, an accent or an emoji shared one row in the
  tagger's table** (`tagger_processed_files.filepath` was `utf8mb4_general_ci`), so one of the pair
  was retagged on every walk and each overwrote the other's mtime. The column is `utf8mb4_bin` now;
  migrate_v37 queues the rows that stood for two files (reason `binary_path`) before it changes the
  collation, and the tagger picks up the twin as a new file. The tagger's folder walk now skips hidden
  folders, as the scanner already did.
- **One 403 during a multi-threaded sweep climbed the backoff ladder once per worker thread and sent
  a push per thread.** `park()` now counts the first refusal of a sweep only and hands the others the
  same answer. A backoff reset from the management page during a sweep is no longer undone when the
  sweep finishes.
- **Redownload could fetch the wrong track, and on YouTube did nothing.** The source was looked up
  with `LIKE '%<name>%' LIMIT 1` (so `Intro.mp3` matched `DJ Intro.mp3`, and `_` matched anything);
  it is now the exact stored path, then the exact file name in the same folder, and a name that
  matches several downloads is a `409` instead of a guess. YouTube ran with `nooverwrites`, so yt-dlp
  reported the file as already downloaded and kept it. Both downloaders now overwrite on a
  redownload, into a staging folder beside the file that is moved over the old one only once it is
  complete: a failed redownload leaves the old file where it was.

<!-- release notes -->

- **A file the tagger cannot read no longer causes an alert every five minutes.** It is retried a
  few times with growing pauses and then set aside; the tagger page shows how many are set aside.
- **Files whose names differ only in capitals, accents or emoji are no longer retagged on every
  pass.**
- **One refusal from SoundCloud or YouTube now costs one step of backoff and one notification**, and
  resetting the backoff during a download round sticks.
- **Redownload fetches the right track and actually replaces the file on YouTube**; if the download
  fails, the old file stays.
