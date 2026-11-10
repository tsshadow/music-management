- **A star set in the app or the web player while music-manager was down never reached
  music-manager.** LMS sent each rating change once, from memory: a connection failure or a 503
  during a deploy dropped it, and nothing sent it again. LMS now writes each rating change to a
  `muma_rating_outbox` table first (LMS database version 128) and delivers it from there once
  music-manager answers, with the listen outbox's backoff (5 s, doubling to 60 s). One row per user
  and item, so three changes during an outage send the last one only, and a cleared rating sends
  the removal. A row waits at most 14 days and the table holds at most 10,000 rows; LMS logs a
  `WARNING` that names the user and the item for each row it drops. One relay in a new
  `mumaoutbox` library sends both outboxes, oldest first, one request at a time.
  `POST /api/rating/lms-event` answers 503 when the path lookup gets no database connection,
  instead of storing the rating under the LMS id, and `/health` has `lms_rating_outbox` next to
  `lms_listen_outbox` (issue #222).

<!-- release notes -->

- A rating you set while the server was restarting is no longer lost: it waits on the server and
  arrives once the restart is done.
