# Management Routes Were Open To Every Account

# status: fixed

# reported problem
A review of the RBAC model against the routers found that most of the management surface was
protected by "is this an enabled account" rather than by a role or a permission. Any account with
the plain `user` role -- every approved access request gets that role -- could:

- read the logs of **any** container on the Docker host through `GET /api/system/logs/{name}`
  (the name was passed to `docker.containers.get` unchecked, so `password manager` or a database
  container worked as well as `muma-manager`), and list the installation's containers;
- add and delete SoundCloud and YouTube downloader sources;
- decide genres and podcasts, write artist/label genre rules and artist redirects, queue the whole
  library for a tagger rescan, and confirm label proposals -- which **moves release folders on
  disk**;
- delete single events or clear the entire event log;
- post a rating webhook naming any `username`, writing ratings into another account's history, and
  read any account's ratings;
- set an artist image from a URL (a server-side request to any address the service can reach,
  including the database, LMS and cloud metadata), upload an image of unlimited size, and start
  the bulk image fetch;
- change their own password without knowing the current one;
- start the lms.db sync, concurrently with the hourly loop, as often as they liked.

And a role holding a narrower permission could do more than it implies: `users.read` listed every
account **including its `api_key`** (`GET /api/users`, and the merge response carried one too) --
and `/api/auth/login` accepts the api_key in place of the password, so that list was a list of
passwords -- while `users.update` was enough to change any account's password, an admin's included.

# Possible reason
`routers/management.py`, `routers/rating.py` and `routers/artist_images.py` each carried a local
copy of `verify_api_key` from before the RBAC model existed. The copy returns the resolved account
for any enabled user and never looks at a role or permission; every route in those files depended
on it alone. Newer routers (`genre_curation.py`, `curation.py`, `festivals.py`) use
`rbac.require_permission`, but the older ones were never migrated, so the RBAC model existed without
being enforced on the routes it was designed for. `events.py`, `news.py` and `radio.py` imported the
management copy, inheriting the gap. The users list selected `u.api_key` because an early admin UI
displayed it; nothing reads it any more.

# solution
- `routers/management.py` no longer has its own `verify_api_key`; it re-exports the canonical
  `routers.users.verify_api_key`. Changing routes are guarded:
  - `rules.manage`: genre/podcast decisions, rename and aliases, artist/label genre rules, artist
    redirects, label-proposal confirm/reject, `POST /api/tagger/rescan` and `/tagger/rescan/file`;
  - admin role: `GET /api/system/containers`, `GET /api/system/logs/{name}`, SoundCloud/YouTube
    account add and delete. `{name}` must pass the same name filter the container list uses, and
    the container Docker resolves must carry exactly that name (Docker also resolves id prefixes),
    otherwise 404.
  - Read-only routes stay open to any authenticated account.
- `DELETE /api/events/{id}` and `DELETE /api/events`: admin only. Listing stays open to any
  authenticated account for the Home Assistant REST sensor, whose key is not necessarily an admin's.
- `POST /api/rating/lms-event` and `/server-event`: system key only (LMS is the only caller and is
  configured with the system key). `GET /api/rating/ratings/{username}`: own ratings, or admin.
- Artist images: `/image/url`, `/image/upload`, `/image/select`, `/image/clear`, `/fetch-missing`
  and `/{id}/fetch-image` need `rules.manage`. The URL route resolves the host and refuses any
  address that is not globally routable (loopback, private, link-local, CGNAT, reserved, multicast,
  IPv4-mapped forms of those), follows redirects by hand re-checking every hop, and streams at most
  10 MB (413 beyond). Uploads are capped at 10 MB, checked before decoding.
- `GET /api/users` and the `POST /api/users/{id}/merge` response no longer return `api_key`.
- `POST|PUT /api/users/{id}/password`: another account's password, and any admin's, needs the admin
  role; a non-admin changing their own must send `current_password`, checked against the bcrypt hash
  (an account without a password yet may set its first one).
- `POST /api/users/sync/*`: admin only, and 409 while a sync runs. The hourly
  `run_lms_db_sync_loop` takes the same module-level lock.
- Tests: `services/music_manager/tests/test_rbac_route_gaps.py` (44 cases; run against the old
  routers, every refusal case fails).
- Not changed, noted for follow-up: `POST /api/scrobble/import/listenbrainz` (proxy in
  management.py) still accepts any account. The DNS-rebinding window between the address check and
  the fetch in the image URL route is not closed.
