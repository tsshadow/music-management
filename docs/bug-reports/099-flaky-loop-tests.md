# Background-loop unit tests failed at random on StopIteration

# status: fixed

# reported problem

Three backend unit tests failed intermittently and blocked releases (2026-09-25/26), and each
passed when run alone:

- `test_scanner_tagger_routers.py::TaggerManagerTest::test_a_round_that_raises_does_not_end_the_loop`
  (release/0.75.2, pipeline 3773, job 37423)
- `test_scanner_tagger_routers.py::TaggerManagerTest::test_every_round_first_queues_a_slice_of_the_deep_run`
  (hotfix/0.74.2, pipeline 3715)
- `test_events_retention.py::RunEventsRetentionTest::test_get_db_connection_raising_is_caught_and_loop_continues`
  (pre-commit hook; GitLab issue #65)

Every time the traceback looked the same: `StopIteration` from `unittest/mock.py`, with
`RuntimeError: Database connection parameters are not fully configured` from
`DatabaseConnector.py:40`, reached through `EventService._write`.

# Possible reason

Two things combined.

1. **The tests ended the loop through a function the whole process shares.** They patched
   `time.sleep` with `side_effect=[None, KeyboardInterrupt]`, written as
   `patch.object(thread_registry.time, 'sleep', ...)` or `tagger_router.time`. That
   attribute is the `time` module itself, so the patch replaced `time.sleep` for every thread
   in the process, not only for the loop under test.
2. **Another thread was sleeping during the test.** The process-wide `event_service` has a
   writer thread. Once any test has run `setup_logging`, every captured log line becomes an
   event (the tagger loop logs `Starting background tagger loop` at INFO). The writer tries the
   real `DatabaseConnector`, which has no configuration in the unit suite and raises. It then
   pauses 1, 4 and 16 s between retries with `time.sleep`. If that call fell inside a test's
   patch window, it took one of the test's two items (or received the `KeyboardInterrupt`). The
   loop then called the mock one time more than the list held: `StopIteration`. The writer's
   `RuntimeError` appears in the same traceback because the patched sleep was called from
   inside its `except` block.

Reproduced locally by running a test that calls `setup_logging('music-manager')` before
`TaggerManagerTest` and `test_events_retention.py`, with output capture off (`-s`). That
changes the thread timing enough to fail about one run in seven, with the exact traceback from
CI. The events-retention timing change from bug report 072 did not cause it. The loop there
calls `get_db_connection` once per round, as the test expects.

# solution

The loops no longer share anything with the tests or with the other threads:

- `thread_registry.run_forever` always pauses with `stop.wait(delay)`. Without a `stop` event
  it creates a private one that nobody sets, so the wait is a plain sleep. It never calls
  `time.sleep`.
- `run_tagger_loop`, `run_scanner_loop`, `run_events_retention` and `run_lms_db_sync_loop` take
  a `stop` event and pass it on. The artist-image CLI's `--daemon` loop waits on a module-level
  `shutdown` event.
- The tests drive these loops with `services/tests/stop_after.py:StopAfter(n)`. It is an
  event whose `wait` never blocks, sets itself on the n-th call and records the requested
  delays, so each test runs exactly n rounds and asserts the backoff arithmetic on
  `stop.delays`. Converted: the four retention tests, the four tagger-loop tests, the two
  scanner-loop tests, the lms-db-sync lock test, the artist-image daemon test, the
  `run_forever` tests, and the listen-backfill "no stop event" test.
- The `EventService` writer pauses between retries on an event of its own (`_retry_pause`).
- `services/tests/in_memory_events_plugin.py` (registered in the root `conftest.py` and kept
  across mock_base worlds) switches every reachable event service to an in-memory writer before
  each test. These are the singleton of the `EventService` module in `sys.modules`, and the
  service behind each `EventLogHandler` on the root logger, which can belong to another world's
  copy (bug report 085). The switch is per instance and permanent, so a queued event written
  after its test has ended does not reach a database either. A test that builds its own
  `EventService()` keeps the real writer. The `recorded_events` fixture exposes what was written.

The importer and downloader loop tests were left alone. They patch `wait` on their own
service's `shutdown` event, which no other thread uses.

Regression tests: `EventServiceTest.test_a_retry_never_calls_the_process_wide_sleep`,
`test_thread_registry.test_the_pause_never_goes_through_time_sleep`, and
`InMemoryEventsPluginTest`. The rule is written down in `CONTRIBUTING.md`.
