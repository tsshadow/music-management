# LMS podcast and ListenBrainz background writes abort the process on a refused commit

# status: fixed

# reported problem
GitLab issue #135, a follow-up to bug report 132. The podcast refresh steps and the ListenBrainz
listen and feedback synchronizers write to `lms.db` on the "Misc" `core::IOContextRunner`
(`lms/main.cpp`). None of them catches a `Wt::Dbo::Exception` around the commit, and the commit
runs in `db::WriteTransaction`'s destructor. The runner catches the exception, then logs FATAL and
calls `std::abort()`. A write the database refuses therefore ends the whole server. A podcast
refresh that died this way would also leave `_refreshInProgress` set, and no refresh would run
again.

The affected sites, relative to `services/music-management-server/src/libs/services/`:
- podcast `CheckForMissingFilesStep` (two writes), `RemovePodcastsStep`, `RefreshPodcastsStep`,
  `RemoveEpisodesStep`, `DownloadPodcastArtworksStep`, `DownloadEpisodeArtworksStep` and
  `DownloadEpisodesStep`;
- ListenBrainz `ListensSynchronizer` (`saveListen`, and `enquePendingListens`, a write
  transaction that only reads);
- ListenBrainz `FeedbacksSynchronizer` (`enqueFeedback`, `onFeedbackSent`, `tryImportFeedback`).

Neither feature is known to be enabled on production.

# Possible reason
Since bug report 132 every LMS write transaction starts with `BEGIN IMMEDIATE` and waits up to 15 s
for the write lock. That lowered the risk, but a lock held for longer than 15 s (music-manager, or
the scanner before bug report 134) still throws. The throw comes either from the
`WriteTransaction` constructor or from the commit in its destructor. These code paths had no catch
for it.

# solution
- **`db::writeGuarded(session, write, onFailure)`** (`database/GuardedWrite.hpp`) captures the
  pattern from bug report 132 once:
  - an outer try around the whole transaction scope, which covers both the BEGIN and the commit;
  - an inner try around the writes, with an explicit `flush()`, so that the destructor's commit
    has nothing left to flush;
  - `discardUnflushed()` in both catches, so no dirty objects are left for the next write on the
    thread;
  - `onFailure` called once, and false returned.
- **Podcasts.** The steps that clean up (missing files, removed podcasts, removed episodes) end
  the refresh with `onAbort()`. That runs `onRefreshDone`, which clears `_refreshInProgress` and
  schedules the next refresh. The per-item writes (a refreshed feed, a downloaded artwork or
  episode) log a WARNING and move on to the next item. They also delete the file they downloaded
  for it, and the next refresh fetches it again. As a last resort, `PodcastService::runStep`
  catches a `Wt::Dbo::Exception` from a step's synchronous part and ends the refresh the same way.
- **ListenBrainz.**
  - `saveListen`, `enqueFeedback`, `onFeedbackSent` and `tryImportFeedback` write through
    `writeGuarded`. A refused write is logged as a WARNING and picked up by the next sync.
  - `enqueFeedback` now sends its HTTP request after the commit instead of inside the
    transaction. `onFeedbackSent` changes the cached feedback count only once the write has
    committed.
  - `enquePendingListens` reads, so it now opens a read transaction.

Tests: `src/libs/database/test/WritePacer.cpp`, suite `GuardedWrite`. A successful write commits.
A refused statement returns false without throwing and calls `onFailure` once. Its discarded
change is not flushed by the next write transaction on the session.
