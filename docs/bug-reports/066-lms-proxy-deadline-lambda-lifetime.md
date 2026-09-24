# LMS Proxy Deadline Wakes a Continuation Wt Already Freed

# status: fixed

# reported problem
Audit item C11 (code reading, 2026-09-23). `core::http::proxyRequest`
(`services/music-management-server/src/libs/core/impl/http/ProxyContinuation.cpp`), used by the
Subsonic `getCoverArt` handler to fetch MuMa artist pictures without holding an HTTP thread, handed
a raw `Wt::Http::ResponseContinuation*` to three callbacks: the send queue's success and failure
callbacks, and the deadline timer that answers 504 when MuMa is too slow. Each ended in
`continuation->haveMoreData()`. Nothing tied the continuation's lifetime to theirs, so the question
was whether Wt could free the continuation before one of them ran.

Nobody has seen a crash that points here. It was found by reading the code.

# Possible reason
Wt's own lifetime rules settle it. The source is identical in Wt 4.11.1 (the Alpine `wt-dev` the unit
suite builds against) and Wt 4.12.5 (`WT_VERSION` in `Dockerfile-release`, the shipped image):
`src/Wt/Http/ResponseContinuation.C` is byte-for-byte the same, and none of the `WResource.C` changes
between them touch continuations.

- `Response::createContinuation()` does `new ResponseContinuation(...)` and passes it to
  `WResource::addContinuation`, which wraps it in a `shared_ptr` and stores it in `continuations_`.
  The caller gets `continuation_.get()`, a raw pointer that owns nothing.
- `continuations_` holds the only lasting reference. The others are temporary: the write callback
  bound in `WResource::handle` (released once `readyToContinue` has run) and the `detectDisconnect`
  callback bound in `readyToContinue` (released with the reply).
- `ResponseContinuation::handleDisconnect()` runs when the client drops the connection while the
  request is parked. It calls `resource->removeContinuation(shared_from_this())` and
  `response_->flush(ResponseDone)`. Once the bound callback goes, the continuation is deleted.
  `readyToContinue(WebWriteEvent::Error)` does the same through `cancel(false)`.
- `WResource::handle` also calls `removeContinuation` after a second pass that does not wait again,
  which is the normal end of every proxied request.

None of this tells the proxy code. So the use-after-free was real, on one path:

1. A client asks for an artist picture. The handler parks on a continuation and MuMa is slow, or
   the send queue is retrying or paused (MR !926 bounds the queue, but it does not stop an answer
   landing late).
2. The client hangs up first. That is common: a phone scrolling past a grid of artists cancels the
   image requests it no longer needs. Wt runs `handleDisconnect` and frees the continuation, and
   `settled` is still false.
3. MuMa's answer arrives, or the deadline fires. Whichever runs first wins `settled.exchange(true)`
   and calls `haveMoreData()` through the dangling pointer. That is a read of freed memory on a Wt
   or Boost.Asio thread, followed by a lock of whatever `mutex_` now points at.

The normal path is safe, and that is why the bug stays hidden. When MuMa answers first, `settle`
wins the flag before Wt frees anything. A deadline completion that was already queued when `settle`
cancelled the timer then finds `settled` set and returns before it touches the pointer. The flag
guards the order *between the three callbacks*, but not Wt's own release of the continuation.

An ad-hoc ASan build of the new unit test against a raw-pointer copy of the state class reports
`heap-use-after-free` in `haveMoreData()` for the disconnect-then-deadline case. The version with
`weak_ptr` passes the same test cleanly.

# solution
The per-request state moved into `detail::ProxyState<Continuation>`
(`impl/http/ProxyState.hpp`), which holds the continuation as a `std::weak_ptr`. It gets that from
`continuation->weak_from_this()`. `ResponseContinuation` derives publicly from
`enable_shared_from_this`, and Wt already owns it through a `shared_ptr` by the time
`createContinuation()` returns. All three endings go through one `settle()`:

- The first caller wins the atomic `settled` flag, as before. Everyone after it does nothing.
- On a win it records the answer and cancels the deadline timer, which is the normal-completion
  cancel. Then it wakes the continuation only if `lock()` still yields one. The strong reference
  from `lock()` keeps it alive for the length of the call. A continuation that Wt has cancelled but
  not yet freed is harmless too, because `haveMoreData()` finds its `resource_` cleared and returns.
- The deadline handler is now just `settle(504, ...)`, so it has no separate path that touches the
  continuation.

The class is templated on the continuation type only because Wt's constructor is private. The unit
test `src/libs/core/test/ProxyState.cpp` uses a fake owned by a `shared_ptr` and covers five cases:
a deadline landing after normal completion and after the continuation was freed, the deadline being
cancelled by completion (the `io_context` runs out of work immediately), a deadline and an answer
each landing after a client disconnect, and a late answer after the deadline has already won.

The regular build has no sanitizer option: nothing in `CMakeLists.txt`, `Dockerfile-build-alpine` or
`scripts/test/` turns on ASan or UBSan, and this change does not add one. The ASan check above was
run by hand, by compiling the single test file with `clang++ -fsanitize=address,undefined` inside the
unit-test image.
