- **The ListenBrainz import list and account deletion are admin matters now** (issue #38, left open
  by bug report 052). `GET /api/scrobble/import/latest` showed every account's last ten imports --
  name, ListenBrainz name and error text -- to anyone signed in; it now returns every account's
  rows to an admin or the system key and only the caller's own to anyone else.
  `DELETE /api/users/{id}` let a plain account delete itself (the check was "self or
  `users.update`"); it now takes `users.update` for every account. **Breaking** for a client that
  relied on self-delete: that call is a `403 Missing permission: users.update` now (no client in
  this repository made it). The last-admin guard is unchanged, and Beheer > Gebruikers shows the
  server's reason when a delete is refused instead of a generic error.

<!-- release notes -->

- **Only admins see everyone's ListenBrainz imports and can delete accounts.** Other accounts see
  only their own imports and can no longer delete themselves.
