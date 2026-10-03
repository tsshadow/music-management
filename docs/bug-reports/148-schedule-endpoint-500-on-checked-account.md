# The Deprecated Schedule Endpoint Answers 500 For A Checked Account

# status: fixed

# reported problem
`GET /api/downloaders/schedule/{source}` answered 500 as soon as one account of the source had a
check record in `downloads_account_checks`. Only a source with no checked account at all got a 200.
`./scripts/typecheck.sh --all` found it as the last error of its backlog (GitLab issues #41 and
#171). The route is deprecated and no consumer in this repository calls it (bug report 084).

# Possible reason
`DatabaseCheckStore().load(source)` returns `dict[str, AccountCheck]`. The endpoint called
`.isoformat()` on each value, as if the value was a `datetime`. `AccountCheck` is a dataclass with
no `isoformat`, so each request with a row raised `AttributeError`. The only test that called the
route (`test_deprecation.py`) gave it an empty store, and `tests/integration/test_router_sql.py` did
not list the route.

# solution
The endpoint reads `check.last_checked_at.isoformat()`. The response shape is the same as
documented: `{"source": ..., "accounts": [{"account": ..., "last_checked_at": "<ISO 8601>"}]}`,
sorted by account.

- `services/music_manager/tests/test_downloaders.py` (`ScheduleEndpointTest`) calls the route with
  `AccountCheck` records, the way the real store answers.
- `tests/integration/test_router_sql.py` lists the route, and `DownloaderScheduleTest` reads a real
  row from MariaDB.
- `backend:typecheck-all` has zero errors now, so it is a hard gate (no `allow_failure`), and
  `tests/ci/test_gitlab_ci_policy.py` keeps it that way.
