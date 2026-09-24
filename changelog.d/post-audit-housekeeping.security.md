- **The nightly production check no longer runs Claude with every permission switched off.** It
  judged a report built from production logs and crash reports -- text anyone who can make prod log
  a line can partly write -- under `--dangerously-skip-permissions`, so the skill's "only GET against
  prod, never merge" was a request, not a limit. `scripts/nightly-prod-check/run.sh` now starts it
  with `--permission-mode dontAsk` (not allowed means denied, never asked) and an explicit
  allowlist: edits only in the fix worktrees and the result file, production only through the new
  `prod-get.sh` (a GET of `/api/...` or `/health`, curl itself denied), `git push` only to
  `nightly-fix/*`, and `glab mr create/view/list` only -- merge, approve, `glab api`, force pushes,
  pushes to `master`/`develop`/`release/*`, ntfy and MCP servers are denied. Pinned by
  `tests/ci/test_nightly_prod_check_permissions.py`.

<!-- release notes -->

- **The nightly production check now runs with an explicit permission allowlist.** It can read
  production but not change it, and can open a fix merge request but not merge one.
