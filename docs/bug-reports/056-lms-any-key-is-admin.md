# Any X-API-Key Made The Caller Whoever `u` Named On LMS's `/muma` Routes

# status: fixed — `MumaResource` verifies every key (its own `api-key`, or MuMa's `/api/auth/verify`) before it grants anything, takes the caller's identity only from the verified credential, and the generic proxy forwards the caller's own key and never the system key

# reported problem
A security review of `services/music-management-server/src/libs/muma/MumaResource.cpp` found
that the `/muma` bridge accepted any non-empty key. Two consequences, both exploitable by anyone
who can reach LMS:

1. **Local admin routes.** `GET /muma/api/admin/subsonic-token?u=<an admin login>&username=<anyone>`
   with `X-API-Key: x` returned that user's Subsonic token, and `PUT` on the same route replaced it
   -- a takeover of every external client account. The same trick opened
   `/muma/api/admin/libraries` (list, add and delete media libraries), `/muma/users/sync` and
   `/muma/users/{id}/settings/{app}` for any user id.
2. **MuMa as the system identity.** For every other `/muma/api/...` route, LMS proxies to MuMa, and
   when the caller had sent no `X-API-Key` header it added the configured MuMa system key
   (`music-management-api-key`). `?apiKey=x` satisfied LMS's check without being a header, so the
   request reached MuMa as `{'type': 'system'}`, which `rbac.has_permission` and
   `rbac.is_admin_auth` grant everything.

nginx sends most of `/muma/api/` straight to MuMa since !833, so on production the second hole was
only reachable through LMS's own port (`LMS_SUBSONIC_PORT`, published for `lms.<domain>`); the
first went through nginx as well, because `/muma/api/admin/` is on the list nginx keeps on LMS.

# Possible reason
The key check was written as a gate against *anonymous* requests, not as authentication:

```cpp
bool authenticated = isPublicAuthPath;
if (!xApiKeyHeader.empty())
    authenticated = true;
else if (apiKeyParam && !apiKeyParam->empty())
    authenticated = true;

db::User::pointer dbUser;
if (userParam)
    dbUser = db::User::find(session, *userParam);
```

The comment above it reasoned that MuMa re-validates the key on every proxied call, which is true
for the proxy -- but the admin and settings routes are answered by LMS itself, from its own
database, and trusted `dbUser`, which came from the bare `u` parameter with no password or token
behind it. The password check only ran when no key had been presented. The proxy's fallback to the
system key was meant for "internal/system-only" calls, but nothing distinguished those from a
caller who simply put the key in the query string.

# solution
The authentication decision moved into `src/libs/muma/Authentication.cpp`, where it is covered by
GTest (`src/libs/muma/test/Authentication.cpp`), and `MumaResource` calls it before any route:

- A key counts only if it is LMS's own `api-key` (constant-time compare) or MuMa confirms it via
  `GET /api/auth/verify`. MuMa's positive answers are cached for 60 s per SHA-1 of the key, at most
  1024 keys; rejections are not cached. `/muma/users/sync` clears the cache, so a disabled account
  stops working here as soon as MuMa announces the change. When MuMa cannot be asked, the answer
  is 503, not 401, so clients keep their key.
- If the key does not hold, a Subsonic `u`/`p` pair is still tried on its own merits.
- The caller's identity comes only from what was verified: the password service's user id for
  `u`/`p`, MuMa's verify answer (`user.id`, `user.is_admin`) for a user key. `u` never names the
  caller when authentication came from a key.
- Media libraries and Subsonic tokens need a verified **admin user**. A system key authenticates
  but is nobody: this server hands its own `api-key` to everyone who logs in through
  `/muma/api/auth/login`, so holding it says nothing about being an admin. `/users/sync` accepts a
  system key (it is MuMa's own notification) or an admin. `/users/{id}/settings/{app}` needs a
  verified user whose **MuMa** id matches `id` -- the id is forwarded to MuMa unchanged, so the
  old comparison with the LMS id compared two different id spaces -- or an admin.
- The generic proxy forwards the caller's own verified key (header, or `apiKey` parameter) and
  nothing else. A `u`/`p` caller reaches MuMa without a key and MuMa answers 401 for whatever
  needs one. The system key is still used for the three calls LMS makes on its own behalf (artist
  image, track refresh, per-user settings), each of which now runs only after the caller has been
  verified -- and, for settings, matched to the target user.

Every consumer was checked. The web frontend calls the admin, refresh and image routes with
`u`/`p` (`LibrariesTab`, `UsersTab`, `TrackList`, `utils.artistImageUrl`), the artist-images tab
with `?apiKey=<its MuMa key>`, and everything else directly on MuMa through nginx. MuMa Mobile
talks to MuMa directly on production and uses none of LMS's own routes. MuMa's
`notify_server_sync_users` sends its system key to `/muma/users/sync`.

Not changed here, and worth a separate decision: `/muma/api/auth/login` still answers every
successful Subsonic login with LMS's `api-key` as the `api_key`. Where that value equals MuMa's
system key, every user who logs in on the web holds the system key for MuMa itself. This fix stops
that key from opening LMS's own admin routes, but not MuMa's. See the GitLab issues.
