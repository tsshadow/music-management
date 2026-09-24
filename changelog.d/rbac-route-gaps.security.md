- **Most of the management API was open to every account, whatever its role.** Three routers
  still carried a pre-RBAC `verify_api_key` that accepted any enabled account, so a plain `user`
  could read the log of any container on the Docker host, add and remove downloader sources,
  decide genres and rules, confirm label proposals (which moves folders on disk), clear the event
  log, write ratings under another account's name, and make the server fetch an arbitrary URL.
  `GET /api/users` also returned every account's `api_key`, which login accepts as a password.
  **Contract change** for the routes below; the web management UI (admins) and LMS (system key)
  pass unchanged, and the Android app uses none of them as a normal user:
  - `rules.manage`: genre/podcast decisions, artist/label genre rules, artist redirects,
    label-proposal confirm/reject, `POST /api/tagger/rescan[/file]`, and the mutating artist-image
    routes (`/image/url`, `/image/upload`, `/image/select`, `/image/clear`, `/fetch-missing`,
    `/{id}/fetch-image`);
  - admin: `GET /api/system/containers`, `GET /api/system/logs/{name}` (only containers the list
    shows, else 404), SoundCloud/YouTube account add/delete, `DELETE /api/events[/{id}]`,
    `POST /api/users/sync/*` (409 while a sync runs, shared lock with the hourly loop);
  - system key only: `POST /api/rating/lms-event` and `/server-event`;
  - own account or admin: `GET /api/rating/ratings/{username}`;
  - `POST|PUT /api/users/{id}/password`: another account's or any admin's password needs admin; a
    non-admin changing their own must send `current_password`;
  - `GET /api/users` and the `POST /api/users/{id}/merge` response no longer carry `api_key`;
  - image URLs resolving to a non-public address are refused (400), and downloads and uploads are
    capped at 10 MB (413).
  An unknown or disabled key on the management routes now answers 403 instead of 401, like every
  other router. See docs/bug-reports/037-management-routes-open-to-every-user.md.
<!-- release notes -->
- **Security: management actions now require the right role.** Rules, downloader sources, container
  logs, event deletion and the server sync were available to every account; they now need the
  curator permission or the admin role. The user list no longer exposes access keys, and changing
  your own password asks for the current one.
