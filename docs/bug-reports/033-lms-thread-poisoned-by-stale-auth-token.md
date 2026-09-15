# One LMS Thread Answers 500 To Everything After A Stale Auth Token Write

# status: fixed — `processAuthToken` rereads the token before the bump, flushes inside its own try, and drops the copy on a stale write

# reported problem
Reopening muma-mobile after a while showed empty lists ("geen data"), on both the debug (313)
and the release (6.36.0) build. Reported 2026-09-15. The reverse-proxy log for the reopen at
16:52:19 UTC has eleven `getSong` calls from the WebView's queue rehydrate answered 500, then
`getSongs`, `getMemories`, `getUser`, `scrobble`, `stream` and `getArtist` from the Kotlin side —
every one of them 500. The LMS log for the same seconds:

```
[WT] WResource: Uncaught exception from handleRequest (aborting request): Stale object, auth_token, id = 4, version = 2392
```

Same thread id (`133521465768752`) on every line, for the rest of the afternoon; other threads
kept answering 200. Earlier 500s at 15:36 and 15:44 carry the same thread id.

# Possible reason
`AuthTokenService::processAuthToken` bumps the token's `use_count`/`last_used` under a write
transaction, guarded since `6e301a2c3` by a `catch (Wt::Dbo::StaleObjectException&)` meant for
exactly the "two requests, same token" race. Three things made that guard a no-op:

1. **Wt::Dbo caches objects per session, and `Db::getTLSSession()` hands each thread its own.**
   `AuthToken::find` on a thread that resolved the token before answers that thread's cached
   copy, at the version it had then. Another thread's bump moved the row on; the copy is a
   version behind, and `modify()` on it is a stale write.
2. **The exception is thrown from the flush, not from `modify()`.** The flush runs in
   `WriteTransaction::~WriteTransaction` → `Transaction::commit()` at the end of the function,
   outside the `try`. That is the "Uncaught exception from handleRequest" — the request in hand
   fails.
3. **The copy stays dirty and stale in the session.** `Transaction::rollback()` (Wt 4.12.5,
   `Transaction.C`) rolls the connection back and drops its own bookkeeping, but does not
   `rereadAll()`. `Session::flush()` flushes *every* dirty object, so the next write transaction
   on that thread — a scrobble, a stream position, anything — throws the same stale write again.
   The thread is poisoned until the process restarts, and it answers 500 to whatever the pool
   routes to it.

Why now: the web UI's boot fires the queue rehydrate as a burst of `getSong` calls while the
Kotlin side (Android Auto tree, scrobbler) is talking to the same server with the same token, so
two threads bump the token within the same minute far more often than the Kotlin UI ever did.

# solution
`AuthTokenService.cpp`: `authToken.reread()` before the bump — under the process-wide write lock,
so the bump lands on what the row holds now; `session.getDboSession()->flush()` inside the
`try`, so the stale write surfaces where the catch is; and `authToken.reread()` again in the
catch, which is `MetaDbo::reread()` → `discardChanges` + drop the copy, so nothing dirty is left
for the next transaction on the thread. `ObjectPtr::reread()` added to `database/Object.hpp` for
it. Regression test `AuthTokenReadPath.aTokenBumpedOnAnotherThreadIsRereadNotRefused` plays the
two-thread race and then asserts an unrelated write transaction on the first thread still
commits.

The black screen reported alongside is a different fault: Android reclaiming the WebView's
renderer of a backgrounded app, with no `onRenderProcessGone` handler (Capacitor asks its
`WebViewListener`s and there were none), so the default killed the process. `CapacitorActivity`
now recreates itself in that case.
