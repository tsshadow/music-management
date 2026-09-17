- A release is cut in two pushes: the empty branch first with `-o ci.skip`, the stabilize commit
  second. GitLab evaluates every `changes:` rule as true on the first push of a new branch, so
  cutting and stabilizing in one push ran `muma:images`, `server:lint`, the integration and e2e
  jobs on a commit that touched only VERSION and the changelogs — the very jobs the CI comment
  claimed a release skipped. Nothing in the pipeline changed; the runbook and the comment now
  describe what actually happens.
