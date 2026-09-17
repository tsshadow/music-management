- CI runs what a push actually touched. A feature branch no longer gets a branch pipeline: its
  first push — the one before the MR exists — ran the entire file (66 job minutes for an 11-file
  frontend change) because a new branch has no commit to diff against, and the MR pipeline that
  followed seconds later ran the 13 jobs that mattered. A push to master, whose tree is identical
  to the release tip that just passed, now runs only the `release:*` sequence instead of re-testing
  backend and server first; the tag and the back-merge no longer wait twenty minutes for that.
- A mobile job that times out no longer leaves its Gradle container running. The runner killed the
  job's shell but not its `docker run`, and the orphan's daemon held the shared Gradle lock, so
  every mobile job on that runner died in sixty seconds with "Timeout waiting to lock journal
  cache" for the next hour. Containers carry a `ci.job` label and `after_script` removes them,
  with `RUNNER_SCRIPT_TIMEOUT` set so that step also runs on a timeout.
