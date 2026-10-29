- **The pre-commit hook could stage the deletion of the whole repository.** Git gives the hook
  `GIT_INDEX_FILE`, and the release-version-check tests inherited it: their throw-away repository
  wrote its four files and its commit into the real index, which then held 3847 deleted files.
  The hook now clears git's variables before the tests, and the tests run git without them
  (bug report 152).
<!-- release notes -->
- Development fix: the pre-commit check no longer touches the commit it checks.
