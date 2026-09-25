# Google Sign-In Trusts Unverified E-mail; Logins Through LMS Reach MuMa Without a Client Address

# status: fixed

Code fixed on both sides. For the per-client limit to see real clients on `lms.<domain>`, LMS has
to look behind Nginx Proxy Manager, which is a setting in production's `lms.conf` and is tracked in
`docs/open-work.md`.

# reported problem
Found in the September 2026 repository audit (items C13 and the rest of A1.13).

1. `POST /api/auth/google` and `POST /api/auth/access-request` accepted any Google ID token that
   passed the signature, audience and issuer checks. The `email_verified` claim was never read, yet
   the token's `email` is what an admin reads when approving an access request, and it becomes the
   username of the account the approval creates.
2. Approving an access request whose e-mail address was already a username -- a person with a local
   account asking for Google access, the case the `link_user_id` option exists for -- ran the
   `INSERT INTO users` anyway, hit the unique index and answered
   `500 Goedkeuren mislukt: (1062, "Duplicate entry ...")`.
3. A token the Google library rejected got `401 Invalid Google token: <library message>`, which
   tells the caller which check failed (expiry, audience, clock skew, certificate fetch).
4. Every login that reaches MuMa through LMS -- the password check LMS makes against
   `/api/auth/login` on every Subsonic request, and `/muma/api/auth/login` on `lms.<domain>` that
   `MumaResource` proxies -- arrived without a client address. MuMa's rate limit could only count
   them per account, so one device stuck on an old password locked the account for everyone, and
   the per-client dimension MR !941 added for nginx did not exist on this route.

# Possible reason
1. `_verify_google_id_token` checked what `verify_oauth2_token` checks plus the issuer, and stopped.
   Google signs the address it has on file whether or not the owner ever proved it; only
   `email_verified` says they did.
2. The approval never looked for an existing username before inserting one, and its catch-all
   `except Exception` turned the database's refusal into a 500 with the driver's text.
3. The `ValueError` from the library was formatted into the 401 detail.
4. `MusicManagementPasswordService` built its request with only `Content-Type` and `X-API-Key`;
   `PasswordServiceBase` knew the client address (it keys LMS's own throttler on it) but did not
   pass it to the backend. `MumaResource`'s generic proxy forwarded only the key and content type.
   On MuMa's side `rate_limit.client_key` took the left-most `X-Forwarded-For` entry from anyone,
   so it could not have trusted a header from LMS without also trusting one from any caller.

# solution
1. `_verify_google_id_token` requires `email_verified` to be `true` (JSON boolean or the legacy
   string `"true"`), else `401 Google account e-mail address is not verified`.
2. The approval checks for the name in any case before creating the account (`identity.username_taken`,
   which bug report 074 added while this was in progress) and answers `409` with a detail that names
   the address and points at `link_user_id`. A duplicate-key error from a race between that check
   and the insert maps to the same `409` instead of the 500.
3. The 401 detail is a fixed `Invalid Google token`; the library's reason is logged at INFO.
4. LMS: `PasswordServiceBase` calls a new `checkUserPasswordFrom(clientAddress, ...)`, which only
   `MusicManagementPasswordService` overrides. Its request (`buildLoginRequest`) carries
   `X-Forwarded-For: <address LMS resolved>`. `MumaResource`'s generic proxy sends the same header
   (`forwardedClientAddress`), replacing whatever the client sent.
   MuMa: `client_key` believes `X-Forwarded-For` only from a peer on `AUTH_TRUSTED_PROXIES`
   (default loopback plus 10/8, 172.16/12, 192.168/16, matching nginx's `set_real_ip_from`) or a
   request carrying the system key, and reads the chain from the right, skipping trusted hops. A
   forged header from anyone else is ignored. A login counts per client and account (10 a minute)
   and per account from anywhere (`AUTH_RATE_LIMIT_ACCOUNT_ATTEMPTS`, 50 a minute), so spreading
   guesses over many addresses still meets a ceiling.

The refresh-token growth from Google logins was already capped by !938 (`rbac.issue_refresh_token`
is used by both logins); verified, not changed.

Tests: `services/auth/test/MusicManagementPasswordOutcome.cpp`, `src/libs/muma/test/Authentication.cpp`,
`services/music_manager/tests/test_rate_limit.py`, `services/music_manager/tests/test_user_requests.py`,
`tests/integration/test_router_sql.py`. Design note: `docs/designs/authentication/technical.md`,
2026-09-25.
