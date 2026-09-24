- **Any `X-API-Key` made the caller whoever `u` named on LMS's `/muma` routes.** The bridge accepted
  every non-empty key without checking it and then took the caller from the bare `u` parameter, so
  `GET /muma/api/admin/subsonic-token?u=<an admin>&username=<anyone>` with `X-API-Key: x` read -- and
  `PUT` replaced -- any user's Subsonic token; media libraries and per-user settings opened the same
  way. The generic proxy also added MuMa's system key whenever the caller sent no header, so
  `?apiKey=x` reached MuMa as the system identity. A key now counts only if it is LMS's own
  `api-key` or MuMa confirms it through `/api/auth/verify` (cached 60 s, cleared on
  `/muma/users/sync`); the caller is whoever that verified credential names; admin routes need a
  verified admin user rather than a system key; and the proxy forwards the caller's own key and
  nothing else. Bug report 037. The same admin route also refuses a Subsonic token shorter than
  16 characters (400, existing tokens untouched), the floor `updateUser` already applied.
<!-- release notes -->
- **Fixed a hole that let any key act as an admin on the server's own management routes.** Keys are
  now verified before they grant anything, and the server no longer lends its system key to
  requests that did not bring their own.
