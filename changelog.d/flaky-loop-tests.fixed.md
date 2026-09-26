- **Three backend loop tests no longer fail at random and block releases.** The tests ended a
  loop by patching `time.sleep` with a finite `side_effect` list. The event writer thread paused
  between database retries with that same process-wide function, so a retry that landed inside
  the test used up its items and it died on `StopIteration`. The writer now pauses on an event of
  its own. `run_forever` and the tagger, scanner, events-retention, lms-db-sync and artist-image
  loops take a `stop` event, and the tests end them through it after an exact number of rounds.
  In unit tests the process-wide event service writes to memory, never to a database. Bug report
  099.

<!-- release notes -->

- **Internal:** random test failures that blocked releases are fixed.
