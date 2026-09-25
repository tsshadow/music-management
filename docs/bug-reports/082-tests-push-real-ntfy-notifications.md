# Local test runs pushed real ntfy notifications ("Downloads failed: <MagicMock ...>")

# status: fixed

# reported problem

On 2026-09-25 Teun's phone received notifications from the milestones topic reading
`Artist Image Fetcher — Background fetch completed. Succeeded: 0 Failed: 1 Downloads failed:
<MagicMock name='mock.ArtistImageFetcher().log_run_summary().get()' ...>`, six times between
03:12 and 07:56 UTC. The events table on production has no such row, so production did not
send them.

# Possible reason

`services/common/config_store.py` calls `load_dotenv()` at import time. On the workstation the
repository's `.env` carries `NOTIFY_URL`, so every pytest run that imports the app, including
pre-commit hooks and the agents' local runs in worktrees below the checkout, built the default
`NtfySink` with the real ntfy URL. The artist-image router test
(`services/music_manager/tests/test_artist_images_router.py`) drives `run_fetch_missing`, which
emits an INFO event with `push=True` (MR !949 added the summary counters that made the mocked
value visible in the text). The event service handed it to the real sink, which posted it to the
milestones topic. The timestamps match local test runs, not CI.

# solution

The root `conftest.py` sets `NOTIFY_URL` to an empty string before any test module is imported.
`load_dotenv()` never overrides a variable that is already set, so the default sink finds no URL
and returns without posting, whatever a developer's `.env` contains. A test that needs a URL
passes its own config object to `NtfySink`. `tests/ci/test_tests_never_push_ntfy.py` fails if the
variable is not blank under pytest.
