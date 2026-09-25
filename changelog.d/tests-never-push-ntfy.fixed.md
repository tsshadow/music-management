- **Running the tests no longer sends real phone notifications.** `config_store` loads the
  developer's `.env` at import time, so a local test run picked up the real `NOTIFY_URL`, and the
  artist-image router test pushed "Downloads failed: <MagicMock ...>" to the milestones topic. The
  root `conftest.py` now blanks `NOTIFY_URL` before anything imports the config store, and a CI
  test pins it. See bug report 082.
