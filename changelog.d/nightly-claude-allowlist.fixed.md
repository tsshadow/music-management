- **The unattended Claude runs on the runner host no longer run with permissions off.** The
  crash triage (which reads crash reports that app users write), the nightly prod check (which
  reads production logs) and the release that the approved-MR watcher starts all used the
  skip-permissions flag. A prompt injected into a crash report or a logged track title could
  therefore do anything the `triage` user can: use the production system key for writes, push
  to any branch, merge. All three now run with `--restricted --permission-mode dontAsk` and a
  per-job allowlist from `scripts/crash-triage/claude-permissions.sh`:
  - production only through one-purpose wrappers (GET, one status PATCH, one ntfy topic);
  - GitLab reads through a wrapper, and pushes only to the job's own branch prefix;
  - only the release run may merge, and then only a green release MR into master;
  - no curl, no `glab api`, and no local test runs (a test run is a shell).
  The units now run a root-owned copy in `/opt/crash-triage/bin`, so a run cannot edit the
  file that sets its own permissions. That copy has to be installed on the runner by hand. See
  bug report 077 and `scripts/crash-triage/README.md`. A CI test now fails when the flag
  appears anywhere outside the docs.

<!-- release notes -->

- **The automatic crash triage and nightly check run on an allowlist.** They can no longer
  do more than their job, even when a crash report or a log line tries to tell them to.
