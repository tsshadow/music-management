# Delete-Then-Insert Writes Were Not Atomic

# status: fixed

# reported problem
Audit item C1 (2026-09-23). The music-manager pool in `services/music_manager/database.py` runs
with `autocommit=True`, and apart from the scanner's file move, the LMS listen reconcile and the
orphan relink, nothing in `services/music_manager` called `conn.begin()`. Every `conn.commit()`
after a sequence of writes therefore committed nothing: each statement had already committed on its
own.

That makes every "replace the set" write two separate changes. A crash, a lost connection or a
failing INSERT between the DELETE and the INSERTs leaves the table empty or half-written, and a
concurrent reader can see the empty state even when nothing fails. Affected, among others: a
genre's parents, a festival's aliases and editions, an artist's or label's external ids, a genre
decision's expansions, the whole genre and artist proposal tables, a scanned track's artist, genre,
label and channel links, and a rematched listen (inserted into `scrobble_listens` but not removed
from the queue, or the other way round).

A concrete trigger that exists today: `PUT /api/rules/festivals/{id}` with an alias longer than 191
characters (the width of `normalized_alias`). MariaDB refuses the INSERT in strict mode after the DELETE already ran, so the request
answered 500, yet the festival carried the new name and had lost every alias it had.

# Possible reason
- The pool's `autocommit=True` is right for the single-statement writes that make up most of the
  code, and those `conn.commit()` calls look like they end a transaction. Nothing in the code or the
  unit tests told a multi-statement write apart from a single one: the mocked connection accepts
  `commit()` either way.
- The integration suite ran every statement against MariaDB, but never a failure half-way through a
  write, so the missing transaction was invisible there too.

# solution
- `services/music_manager/database.py` has `transaction(conn)`: `begin()` on entry, `commit()` on
  success, `rollback()` and re-raise on any exception (a failing rollback is logged and never hides
  the original error). The pool default stays `autocommit=True`; `BEGIN` suspends it for the block
  only, and DBUtils rolls back a connection closed mid-transaction on its way back to the pool.
- Every delete-then-insert in music-manager runs inside it, plus the multi-statement account writes
  (approve/unapprove an access request, delete and merge a user) and the song pin/split. The full
  list is in [the technical design](../designs/db-transactions/technical.md). No write ran across two
  connections.
- `scanner.process_file` now always opens its transaction instead of only when a file moved, so a
  track's links are never visible half-rewritten.
- Tests: `test_database_transaction.py` for the helper; one `*AtomicityTest` per write in the router
  test modules asserting `BEGIN` < DELETE < INSERT < `COMMIT` and `ROLLBACK` without `COMMIT` on a
  failure; `tests/integration/test_router_sql.py::TransactionTest` proves on a real MariaDB that a
  rolled-back DELETE leaves its rows, that a pooled connection is clean afterwards, and that the
  festival update above now keeps its name and aliases.

Not wrapped, deliberately: deletes that remove a parent and its children in sequence with no INSERT
(a news source, a radio channel, an artist-curation undo) and the artist-curation `decide`. Each
leaves at worst an orphan the next run removes. They were wrapped later: `decide` and `undo` in
[bug report 080](080-artist-redirect-chains-and-portrait-reset.md), the news source, the radio
channel and the podcast merge in [bug report 113](113-parent-child-deletes-without-transaction.md).
