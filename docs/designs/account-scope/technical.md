# Account scope of the import list and account deletion — Technical Design

Implements [functional.md](functional.md) (GitLab issue #38, follow-up of bug report 052).

## Data Model

None. `scrobble_imports.username` already holds the account's stored spelling (`_history_owner`).

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/scrobble/import/latest` (and its twin in `management.py`, which delegates) | API key | Unchanged shape. Admin role or system key: the ten newest rows of every account. Any other account: `WHERE username = <own username>`, ten newest. | 401 without a valid key; 500 without a database. |
| `DELETE /api/users/{user_id}` | API key with `users.update` | `{"status": "ok"}` | **403 `Missing permission: users.update`** for any account without it, the caller's own id included (**breaking**: self-delete used to pass); 404 unknown id; 409 last enabled admin (bug report 052); 500 on a database failure. |

The import list keys on the admin *role* (`is_admin_auth`, as `_may_write_history_for` in the same
router does), not on a permission: `users.update` alone does not widen it.

## Cross-App Impact

- Frontend: Management is admin-only and already disabled the delete button without `users.update`;
  `UsersTab.svelte` now shows the server's `detail` when a delete is refused (403/409) instead of a
  generic error. `ScrobbleTab.svelte` needs no change: an admin sees what it saw before.
- MuMa Mobile and LMS call neither endpoint (checked: `MumaAPIDefinition.kt` has no such route).

## Technical Acceptance Criteria

1. `test_rbac_route_gaps.py::DeleteUserScopeTest`: a plain account is refused for itself and others
   with no SQL run; `users.update`, admin and the system key delete; the last admin is still 409.
2. `test_rbac_route_gaps.py::LatestImportsScopeTest`: a plain account (and `users.update` without
   the admin role) gets the `WHERE username = %s` query with its own name; admin and system key get
   the unscoped one; the `management.py` twin applies the same scope.
3. `tests/integration/test_router_sql.py`: on MariaDB a plain account's key lists only its own rows
   while the system key lists both, and a plain account's self-delete is a 403 that leaves the row.
4. `tests/unit/usersTabDelete.test.js`: a refused delete shows the server's reason.

## Related Docs

- `docs/bug-reports/052-the-last-admin-could-demote-itself.md`
- `docs/api-specification.md` (User & Settings Management, ListenBrainz import)
