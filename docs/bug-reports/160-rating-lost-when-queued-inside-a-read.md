# A Rating Set In LMS Is Lost When Another Connection Commits At The Same Moment

# status: fixed

# reported problem
Since the rating outbox (issue #222, merged 2026-11-10) the rating tests fail now and then. `muma:e2e` times out on "the rating of N to reach music-manager (last result: None)" in `tests/bdd/test_rating_roundtrip_steps.py`, and `muma:contracts` times out on the last rating made during an outage in `test_relay_outbox_outage.py`. 12 e2e jobs and 3 contract jobs failed this way between 2026-11-11 and 2026-11-12, and the next pipeline on the same code often passed (issue #242).

# Possible reason
`MusicManagementBackend::onRatingChanged` in LMS's feedback service read the rated track, release or artist in a read transaction and queued the rating while that transaction was still open. The outbox write nested in it cannot start as `BEGIN IMMEDIATE`, so SQLite upgrades the read snapshot to a write. In WAL mode SQLite refuses that upgrade when another connection committed after the snapshot was taken. That other connection is often the relay, which removes the row it just delivered, or music-manager writing to `lms.db`. The relay logged `[MuMa outbox] Cannot queue the rating ... it is lost: database is locked` and the rating never left LMS.

A removed rating is queued without a read transaction, and a listen is read in a scope that ends before it is queued. Neither has the fault, so the contract test for a cleared rating passed in the same runs.

# solution
Each `onRatingChanged` reads what it needs in a read transaction that ends before the rating is queued, the same way the listen path does. The GTest case `aCommitElsewhereWhileTheRatingIsReadDoesNotLoseIt` in `services/music-management-server/src/libs/services/feedback/test/MusicManagementBackend.cpp` commits on another connection just before the rating is queued. Before the fix the outbox stayed empty, after it the rating is queued and sent.
