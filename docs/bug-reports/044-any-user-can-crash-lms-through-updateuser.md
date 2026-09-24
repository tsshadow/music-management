# Any User Can Crash LMS Through `updateUser`

# status: fixed — `updateUser` range-checks every enum setting, the feedback and scrobbling services look a backend up with `find()` and skip a missing one, and five neighbouring defects in the Subsonic layer found in the same review are fixed alongside

# reported problem
A review of the LMS fork (`services/music-management-server`) found that any logged-in user could
take the whole server down with one request:

```
GET /rest/updateUser?u=<me>&...&username=<me>&feedbackBackend=7
```

followed by rating any track. The same review turned up five more defects in the same layer:

1. **Crash via `updateUser`.** `/updateUser` only checks "yourself or an admin", which is right --
   the web player's settings page and password change use it for the caller's own account -- but
   the handler cast the raw integers for `feedbackBackend` and `scrobblingBackend` straight to
   their enums. The next rating then ran `_backends[*backend]->onRatingChanged(...)` in
   `FeedbackService`: `operator[]` on the backend `unordered_map` inserts a null `unique_ptr` for
   an unknown key and the call dereferences it. A segfault for every user, not an exception for
   one request. `ScrobblingService` had the same pattern for every listen. `operator[]` also
   *writes* to that map, which every request thread shares, so even valid keys were a data race.
2. **Clearing a rating never reached MuMa.** `FeedbackService::setRating(..., nullopt)` deleted the
   rated row and then notified the backend with the id of the row it had just deleted.
   `MusicManagementBackend` looked that id up, found nothing and sent nothing. The rating sync is
   one-way, so MuMa's `rating_tracks` kept the old star forever, and everything MuMa derives from
   ratings (dynamic playlists, daily mixes, favourites) kept acting on it.
3. **`getSpotifyTracks`/`getSpotifyPlaylist`/`getSpotifyHistory` took any `count`.** The `int` was
   cast to `size_t` unchecked, so `count=-1` became `SIZE_MAX` and walked the whole library in one
   request; history then did one extra query per listen.
4. **Deduplicated pages skipped tracks.** With `deduplicate=true`, `nextOffset` advanced by every
   row fetched in the last scan batch, including the rows after the page had already filled. Up to
   `scanBatchSize - consumed` tracks per page were never shown on any page.
5. **A 429 from MuMa froze the LMS-to-MuMa queue.** `SendQueue` put a 429 back at the head of the
   queue with no retry limit and paused the whole queue (30 s by default). A proxied call, whose
   caller wants MuMa's answer verbatim, paused ratings and scrobbles as well. The queue itself had
   no length bound, so a MuMa outage grew memory for as long as it lasted.
6. **Subsonic tokens could collide.** `auth_token(domain, value)` had a plain index. Two users with
   the same token made `AuthToken::find` throw `NoUniqueResult`: a 500 for both. `updateUser`
   accepted a token of any length.

# Possible reason
Each of these is a missing check at a boundary that trusted its input:

- `updateUser` is the fork's own endpoint (upstream LMS answers it with "not implemented"), and its
  settings were added one `static_cast` at a time, mirroring the web UI's `<select>`s rather than
  the enums behind them.
- `FeedbackService` and `ScrobblingService` indexed a map with `operator[]`, which is only safe
  when every key is known to be present.
- The rating-removed path reused the rating-changed notification, whose contract is "look the row
  up", after making sure there was no row to look up.
- The paging code converted request integers to sizes without a sign check or an upper bound.
- `SendQueue` treated a 429 as "retry this first, forever".
- The uniqueness of a token was assumed by `find` but never enforced by the schema.

# solution
Fixed in the `fix/lms-subsonic-hardening` merge request, one change per defect:

1. `endpoints/UserSettingsValidation.hpp` maps every enum setting `updateUser` takes
   (`feedbackBackend`, `scrobblingBackend`, `subsonicDefaultTranscodeFormat`,
   `subsonicArtistListMode`, `uiArtistReleaseSortMethod`, each entry of
   `uiInlineArtistRelationships`) to its enum or to nothing; an unknown value is a Subsonic
   "bad parameter" error and nothing is written. `subsonicDefaultTranscodeBitrate` must be an
   allowed bitrate (the setter asserted it already). `FeedbackService::findBackend` and
   `ScrobblingService::findUserBackend` use `find()`, log and skip a missing backend, and never
   insert. `updateUser` stays self-service: the web player's settings and password change depend
   on it, and there is no upstream behaviour to restore.
2. `FeedbackService::setRating` captures a `RatingRemovedEvent` (object type and id, username,
   track path, previous rating) inside the write transaction that deletes the row, and calls the
   new `IFeedbackBackend::onRatingRemoved`. `MusicManagementBackend` sends
   `{"event": "rating_removed", "rating": 0, ...}`; `POST /api/rating/lms-event` deletes the
   matching `rating_tracks` row for `rating_removed`, and for a `rating_changed` with a rating of
   0 or less. A new `test-feedback` GTest suite and `test_rating.py` cover both ends.
3. `endpoints/SpotifyPaging.hpp::parseRange` refuses a negative `offset`/`count` and clamps
   `count` to 1000 (the largest legitimate request is 500: the web player's biggest page size and
   Android Auto's browse page). History loads listens and their tracks in one query,
   `Listen::findWithTrack`.
4. `collectDedupedPage` advances `nextOffset` by the rows it actually consumed, and reports
   `moreResults` when the page cut a batch short.
5. A 429 on a `treatAnyStatusAsSuccess` request goes to the caller as its answer and pauses
   nothing; any other request is retried at the back of the queue at most three times and then
   failed. The queue holds at most 1000 unsent requests; beyond that the oldest request of the
   lowest non-empty priority is failed with a warning. A request aborted at shutdown without an
   `onAbortFunc` now gets its `onFailureFunc`, so a caller waiting on a promise is released.
6. Migration V121 removes every token value shared by different users (neither may keep a key the
   other also holds; both re-issue), keeps the oldest row where one user holds a value twice, and
   replaces the plain index with `auth_token_domain_value_unique_idx`. `updateUser` refuses a token
   shorter than 16 characters and one another user already holds.

Follow-up, done in MR !917: the `/muma` token route (`MumaResource.cpp`, not touched here to avoid
conflicting with !917) now applies the same 16-character minimum through
`muma::subsonicTokenProblem`, answering 400 without touching existing tokens. MumaResource's proxy
waits on its promises with a timeout and sets no `onAbortFunc`; the new fallback to
`onFailureFunc` releases them at shutdown without a change there.
