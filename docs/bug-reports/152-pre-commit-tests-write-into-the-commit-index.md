# Pre-Commit Tests Write Into The Commit's Index

# status: fixed

# reported problem
On 2026-10-29 a commit of five files in a worktree failed in the pre-commit hook with 2 failed
tests and 12 errors, all in `tests/ci/test_release_version_check.py`. Afterwards `git status`
showed 3847 files staged as deleted, every file of the repository as untracked, and staged
changes to `VERSION`, `CHANGELOG.md`, `RELEASE_NOTES.md` and
`services/muma-mobile/app/build.gradle`. The working tree was intact. A second `git commit`
without the failing tests would have committed the deletion of the whole repository.

# Possible reason
Git runs the pre-commit hook with `GIT_INDEX_FILE` set to the index of the commit it is making,
and in a worktree also with `GIT_DIR`. The hook runs `scripts/test/music-management-unit.sh`,
which inherits both. The fixture of `test_release_version_check.py` builds a throw-away repository
with `git init`, `git add .` and `git commit`, and its `_git` helper passed the environment on
unchanged. So `git add` wrote the four fixture files into the real index, and the fixture's
`git commit` replaced the rest of that index with the throw-away tree. In CI no hook runs, so the
tests pass there.

# solution
- `scripts/hooks/pre-commit` removes git's local variables
  (`unset $(git rev-parse --local-env-vars)`) before it runs the unit tests, so no test sees the
  commit's index.
- `_git` and the `git clone` in `test_release_version_check.py` run with every `GIT_*` variable
  removed, so the tests are hermetic when someone runs them from another hook or script too.
- `test_git_in_the_throw_away_repo_ignores_an_inherited_index` sets `GIT_INDEX_FILE` to a decoy
  and fails if `_git` writes to it. It fails against the old helper.
- A worktree in this state recovers with `git reset` (mixed): it rebuilds the index from `HEAD`
  and leaves the working tree as it is.
