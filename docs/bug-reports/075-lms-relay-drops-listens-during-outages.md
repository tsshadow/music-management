# LMS's Relay Drops Every Listen Made While MuMa Is Down

# status: fixed

# reported problem

Bug report 071 found that LMS's relay of listens to MuMa is best-effort. On 2026-09-25 LMS
recorded four listens for "Teun" between 05:26 and 06:09 UTC, and MuMa has only the last one.
The other three fell inside the 0.73.2 deploy. The LMS listen reconcile finds 1,453 LMS-only
listens overall. Every deploy, and every other MuMa outage, loses the listens made during it.
The only repair was a hand-started `POST /api/scrobble/reconcile/lms` with `insert_lms_only`.

# Possible reason

`MusicManagementBackend::sendScrobble` posts each listen to `/api/scrobble/event` through an
in-memory `SendQueue`
(`services/music-management-server/src/libs/services/scrobbling/impl/musicmanagement/MusicManagementBackend.cpp`).
That queue retries a transport error twice, back to back, with a 5 s timeout each. It drops any
non-200 answer without retrying (`src/libs/core/impl/http/SendQueue.cpp`), and it lives in memory,
so an LMS restart loses whatever is still queued. When MuMa is unreachable or answers 5xx for
more than about 15 seconds, the relay loses every listen it sends in that time.

LMS's own `listen` table (`backend = 0`, Internal) is written by the same call and never loses
anything, so it already holds every listen the relay dropped.

# solution

Open-work listed two options: an outbox in LMS, or MuMa pulling recent LMS-only listens on a
schedule. We chose **MuMa pulling**. It is smaller and needs no C++ change. It reuses the
reconcile's tested classification, including the 600 s same-play guard and case-insensitive
usernames from bug report 070. It survives LMS restarts, because LMS's `listen` table is the
durable outbox.

- New `lms-listen-backfill` thread in music-manager (`services/music_manager/lms_listen_backfill.py`,
  started from `main.py`, run through `thread_registry.run_forever`, listed in `/health` `threads`).
  Every `lms_listen_backfill_interval_minutes` (15) it runs `scrobble_reconcile.backfill()` over the
  last `lms_listen_backfill_window_hours` (48) of LMS listens. It inserts the `insertable` LMS-only
  listens older than 30 minutes, with `source = 'lms-backfill'` and LMS's start time. The 30-minute
  wait leaves the live relay and the app's own scrobble time to arrive first. `shifted` is never
  applied, and nothing existing is updated. The UNIQUE `(username, listened_at, track_id)` key makes
  a second round a no-op.
- `read_lms_listens`, `load_muma_listens` and `load_unmatched_times` take a `since` bound, so a round
  never scans all of history. LMS is bounded through `julianday()`. MuMa's side is read from
  `since - 1200 s`, matching `listened_at` or `created_at`, so every LMS listen in the window is
  judged against the same neighbours a full run would use.
- Config keys in `config_store.py`, group "Scrobbling", shown on Beheer > Config:
  `lms_listen_backfill_enabled` (on), `lms_listen_backfill_interval_minutes`,
  `lms_listen_backfill_window_hours`. They are read again every round.
- Logging: one INFO line per round that inserted something, DEBUG otherwise. A run of failed rounds
  logs one WARNING.
- `run_forever` accepts an optional `stop` event, which the loop uses.
- The historical backlog older than the window is still a one-off manual run: a dry run with
  `GET /api/scrobble/reconcile/lms`, then `POST` with `{"insert_lms_only": true}`. This is
  documented in `docs/designs/ratings-scrobbling/technical.md` and `docs/api-specification.md`.

Tests: `services/music_manager/tests/test_lms_listen_backfill.py` runs the real classifier against
a stateful fake MariaDB and an in-memory `lms.db`. It covers:

- a recent lost listen is inserted once, and the next round is a no-op;
- a lost listen older than the window is not touched, and the bound reaches both sides;
- a listen from the last 30 minutes waits;
- `shifted` is never applied;
- the app's scrobble a minute later blocks the insert;
- a muma listen just before the window still guards;
- a zone mismatch writes nothing;
- log levels;
- config defaults and validation;
- the thread appears in `/health` and stops on its event.

`tests/integration/test_scrobble_reconcile.py` runs the same round against MariaDB, and
`tests/integration/test_router_sql.py` runs the new windowed queries against the real schema.

**Follow-up (issue #67, 2026-09-27): LMS got the outbox too.** Teun chose to have both. Since
LMS database version 125 every listen for music-manager is written to `lms.db`'s
`muma_listen_outbox` first. A background relay on LMS's io_context delivers it in order, with
backoff (5 s doubling to 60 s), and deletes it only on a 2xx or 409. The outbox survives LMS
restarts and is bounded at 10,000 listens and 14 days, with a WARNING per drop. music-manager's
`/health` shows its size and oldest entry per LMS (`lms_listen_outbox`). The backfill loop above
stays as the safety net behind it. Design:
[docs/designs/lms-listen-outbox/](../designs/lms-listen-outbox/technical.md).

On production (2026-09-25): the loop shipped in 0.74.0, and the historical backlog older than the
48-hour window was reconciled once by hand -- 160 listens inserted, 0 collisions. The 1,319
LMS-only listens that remain stay out on purpose: each has a MuMa listen within 10 minutes of it,
which is the guard that keeps the app's own scrobble from being counted twice.
