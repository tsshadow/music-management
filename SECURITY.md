# Security

## Reporting a vulnerability

This is a personally hosted music library, not a public service. Report anything
security-relevant privately to the maintainer rather than in a public issue:
open a **confidential** issue in GitLab, or mail the address on the commits.

## What is scanned, and when

`scripts/ci/dependency-audit.sh` runs `pip-audit` over all five requirements
files and `npm audit` over `services/frontend/package-lock.json`. The
`security:dependency-audit` job runs it on a schedule, on the default branch,
and manually on demand.

It audits what this repository *declares*, not what happens to be installed on
a runner, so every finding points at a line someone can change here. Transitive
packages are covered too -- that is how the starlette advisories behind fastapi
show up. Fix one by bumping the pin in the requirements file it names.

The runner has no pip-audit, so that half runs inside `python:3.11-slim` (see
`scripts/lib/python-tooling.sh`); `npm audit` stays on the host. The image is
3.11 rather than 3.13 on purpose: `numpy~=2.0.2` has no 3.13 wheel, and
resolving it there attempts a source build that fails for reasons unrelated to
security.

The job is `allow_failure` because it queries the advisory database over the
network, and a transient outage should not turn the default branch red -- not
because its findings are optional.

Findings that genuinely cannot be fixed yet go in
`security/accepted-vulnerabilities.txt` -- one advisory ID per line, with a
reason and a way out. That file exists so an exception has to be written down,
rather than the whole job being marked `allow_failure`. Review the entries
whenever the dependency they belong to is upgraded.

## Known accepted risk

The `starlette` advisories listed in `security/accepted-vulnerabilities.txt` all
clear at once when `fastapi` moves past `~=0.111`, which constrains starlette to
`<0.38`. That is a migration rather than a version bump; the FastAPI TestClient
suite under `services/music_manager/tests/` plus `tests/integration/` is what
should validate it.

## Authentication model

Summarised here because it affects what counts as a vulnerability;
[docs/authentication.md](docs/authentication.md) is the full description.

* Authorization is derived from a role and its permissions
  (`services/music_manager/rbac.py`), never from a hardcoded username or an
  inline `role == 'admin'` check. `is_admin` survives only as a derived,
  read-only convenience field.
* A user's `api_key` is an access token: holding it grants full API access via
  the `X-API-Key` header. `/api/auth/login` therefore also accepts it in place
  of the password, which grants no additional privilege and is how a
  Google-linked account -- which has no password on this side -- authenticates
  Subsonic and streaming calls.
* Because the api_key is password-equivalent, `/api/auth/login`,
  `/api/auth/refresh` and `/api/auth/setup` are rate limited
  (`services/music_manager/rate_limit.py`). Exceeding the limit returns 429.
  Only rejected attempts count -- LMS re-checks the password here on every
  Subsonic request, so counting successes logged the whole installation out.
  A login is counted per client and account (10 a minute) and per account from
  anywhere (50 a minute). The client is named by `X-Forwarded-For`, which is
  believed only from a trusted network (`AUTH_TRUSTED_PROXIES`, default the
  private ranges and loopback) or a caller holding the system key, and read
  from the right, so a client cannot pick its own bucket from outside the LAN.
  Both proxies in front of MuMa -- nginx and LMS -- send the client address
  they resolved, never the client's own header
  (docs/bug-reports/079-google-login-unverified-email-and-lms-login-limit.md).
* A Google ID token is accepted only when its `email_verified` claim is true;
  the address becomes the username of an approved account. A rejected token's
  401 says only that it was rejected, not which check failed.
* Passwords are stored as bcrypt hashes. Revoking sessions clears the api_key
  and every refresh token in one step. A non-admin changing their own password
  must present the current one; another account's, or an admin's, needs the
  admin role.
* There is one key check, `routers.users.verify_api_key`: missing or unknown
  key 401, disabled account 403, database unreachable 503. A router must
  not carry its own copy: three did, from before RBAC, and accepted any enabled
  account on every management route (docs/bug-reports/037-management-routes-open-to-every-user.md); two more swallowed
  every error into 401 "Invalid API key" (docs/bug-reports/052), and the wrappers left
  after that are gone too (docs/bug-reports/065; `test_router_api_key_dependency.py` fails on a
  new copy). A route that changes rules
  needs `rules.manage`; one that operates the installation (container logs,
  downloader sources, event deletion, the lms.db sync) needs the admin role; a
  webhook that names the acting user in its body (the LMS rating webhook)
  accepts only the system key. `services/music_manager/tests/test_rbac_route_gaps.py`
  pins each of those.
* No response lists another account's `api_key`, and no login hands out a key
  that is not the caller's own. The web login (`/muma/api/auth/login`) is
  MuMa's login; LMS used to answer it with its own `api-key` for every user.
  A system key left in a browser from that login ends the session at startup
  rather than counting as an administrator.
* A user key writes only its own history: `POST /api/scrobble/event` and the
  ListenBrainz import refuse (403) another account's `username` unless the
  caller is an admin or the system key.
* The last enabled admin cannot be deleted, demoted or disabled (409), and
  first-time setup creates exactly one admin even under concurrent requests.
* Login does not reveal whether a username exists: an unknown name gets the
  same 401 text as a wrong password and still pays for one bcrypt check.
* Refresh tokens are capped at 10 per account (oldest pruned on issue, and
  daily across all accounts); revoked rows go after 30 days.
* A URL the server fetches on a caller's or a provider's behalf (artist image
  URLs, pasted or from an API answer) must resolve to globally routable addresses
  only; the host is resolved once and the connection goes to that checked address
  (original name as `Host`, TLS SNI and certificate name), so a DNS answer that
  changes between check and fetch cannot redirect it inward. Every redirect hop is
  re-checked, at most three, and the body is capped at 10 MB and 10 seconds; see
  `artist_image_fetcher/safe_fetch.py` and
  [bug report 114](docs/bug-reports/114-artist-image-dns-rebinding.md).
* LMS's `/muma` bridge verifies a key before it grants anything: it must be
  LMS's own `api-key` or a key MuMa confirms through `/api/auth/verify`, and
  the caller's identity comes only from that verified credential or from a
  checked Subsonic `u`/`p` pair -- never from the bare `u` parameter. Its
  proxy forwards the caller's own key and never substitutes the system key.
  See [docs/authentication.md](docs/authentication.md#the-lms-muma-bridge-mumaresource)
  and [bug report 056](docs/bug-reports/056-lms-any-key-is-admin.md).

## The system API key

Service-to-service calls authenticate with a *system* key rather than a user
account. `rbac.has_permission` and `rbac.is_admin_auth` both return True for
`{'type': 'system'}` unconditionally, so this key is the most privileged
credential the installation has -- strictly more than an admin login, because no
role lookup stands between it and any endpoint.

It is resolved in exactly one place,
[`services/music_manager/api_key.py`](services/music_manager/api_key.py), from
`API_KEY` or, failing that, `MUMA_API_KEY`. Resolution **fails closed**: neither
variable set means there is no system key, and every `X-API-Key` falls through to
the per-user lookup in `routers.users.verify_token`. A missing key can cost
service-to-service calls their access; it must never grant access instead.

Nothing may reintroduce a literal default. Ten routers and fourteen test modules
used to end their key expression with `or '<a uuid>'`, and that uuid was the
deployment's real `MUMA_API_KEY` -- read access to this repository was
unrestricted admin access to the API. `services/music_manager/tests/test_api_key.py`
walks the tree and fails if that literal reappears in any Python source.

## The Android app

What `services/muma-mobile` does with credentials, since bug report 054:

* **TLS is verified.** The one server the app signs in to has a publicly trusted
  certificate, and `StaticServers.ALLOW_SELF_SIGNED_CERTIFICATE` is `false`, so
  the Subsonic client uses the system trust store. `network_security_config.xml`
  refuses cleartext except to `localhost` (the Capacitor WebView's own origin)
  and trusts user-installed CAs only in debuggable builds.
* **Subsonic requests are signed with the Subsonic token, not the password.**
  LMS checks the salted `t`/`s` form against the per-user Subsonic API token,
  so the app (native client and web shell alike) fetches its own token from
  `GET /api/auth/subsonic-token` and signs every `/rest` URL with
  `t=md5(token + salt)&s=salt`. The password travels only in the MuMa login's
  POST body. There is no password fallback any more (issue #72): a client
  without a stored token fetches one before its first Subsonic request, and
  while none can be had it sends no Subsonic request at all -- the native
  client throws `SubsonicTokenUnavailableException` before the request leaves
  the device, the web player's `authParams` stays empty -- and says "sign in
  again" or "server unreachable" instead. The browser web player signs the
  same way.
* **No password is stored after sign-in** (issue #101). Neither the app's
  native side nor the web player (native preferences, WebView and browser
  localStorage) keeps the password once a sign-in has traded it for the MuMa
  API key and the Subsonic token; a password an older build stored is removed
  on the first start. "Signed in" is an explicit flag. A MuMa key the server
  refuses (401) ends the session and shows the sign-in page -- it is not
  silently traded for a new key -- and Android Auto then says to sign in on the
  phone. The MuMa API key is now the one long-lived credential on the device.
* **Credentials on Android are encrypted at rest** (issue #115). The MuMa API
  key and the Subsonic token are sealed with AES-256-GCM under a key held by
  the Android Keystore (hardware-backed where the device has it, never
  readable by the app), and the file holding the ciphertext is excluded from
  auto-backup and device transfer. A key the Keystore lost or invalidated, or
  a backup restored without the credentials, leaves the app signed out rather
  than crashing. An update moves a key an older build kept in the plain
  preferences on its first start and removes the plain copy.
* **Logs are redacted before they leave the phone.** `LogRedaction` masks the
  `u`/`p`/`t`/`s`/`apiKey`/`password` query parameters, credential headers,
  credential-named settings and credential-named JSON members in every
  ring-buffer line, which is what diagnostics reports upload; the copy saved to
  Downloads is redacted the same way. The debug build's OkHttp logging redacts the same names.
* **Exported content providers serve only their own files.** The album-art
  provider must stay exported for Android Auto, the media notification and the
  widget, so it refuses any key that could resolve outside the art cache.
* **No hoster credential is compiled in.** The update check asks apk-hoster as
  its public read-only `guest` account; the upload password lives only in CI.
* **WebView remote debugging is debug-only** (Capacitor's default when the key
  is absent from `capacitor.config.json`).

## Container hardening

Every production container runs with `no-new-privileges`, `cap_drop: [ALL]` plus a minimal
`cap_add`, and a `pids_limit`; LMS, its nginx proxy and autoheal also have a read-only root
filesystem. The per-service sets, the reasons, and what is still open (non-root users and
read-only roots for the muma images, Firefox) are in `muma-ops docs/deployment-production.md`, "Container
hardening"; `tests/ci/test_compose_hardening.py` pins them.

## Secrets

* `.env` is gitignored and must never be committed; `.env.example` documents the
  keys without values.
* The `release:check-secrets` CI job fails a release pipeline immediately when a
  required key inside a file-type CI/CD variable is missing. GitLab cannot
  enforce that itself, so that job *is* the requirement -- a release pipeline
  that skipped or removed it is not passing.
* Store the GitLab token for pushing in a credential helper rather than
  embedding it in the remote URL: a token in `.git/config` is plain text on
  disk and ends up in the output of anything that prints the remote.
* `scripts/import_lms_users.py` takes the remote host's credentials from
  `REMOTE_PASS` and has no default. Unset it and the script uses key-based
  authentication, which is the better path; when it is set it reaches `sshpass`
  through the environment (`-e`), never through `-p`, which would expose the
  password in the process list to every other user on the machine.
* **No secret on any command line.** `ps` and `/proc/<pid>/cmdline` show an
  argv to every account on the machine, including a process inside a container
  seen from the host. MariaDB clients get `MYSQL_PWD` (to `docker exec` as
  `-e MYSQL_PWD` without a value), `docker run` gets `-e NAME` without a value,
  curl gets a header through `-H @<(printf 'X-API-Key: %s\n' "$KEY")` and a
  body through `--data-binary @-`, values for a remote shell travel on ssh's
  stdin, `sshpass` uses `-e`. `tests/ci/test_no_secrets_on_command_lines.py`
  scans every shell script, YAML file, Dockerfile and Gradle file and fails on a
  new occurrence; throwaway credentials of the disposable test stack are
  allowlisted there with a reason. See bug reports 038 and 125.

### Rotating a leaked secret

Removing a committed secret from the working tree does not unpublish it -- every
clone still holds it, and `git log -S'<the value>'` finds it in seconds. Deletion
is the second step; the first is always to rotate the credential at its source,
after which the copy in history is worthless.

The history of this repository was rewritten once, on 2026-10-29 (#189), after every
credential committed until then had been rotated: `.env`, `.server-env.json` and the
personal data in old commits are gone, and `.gitleaksignore` is empty. A rewrite is not
the answer to a new leak; rotation is.

The system API key described above is in this position. It was committed until
the `api_key.py` change, so it must be replaced in `.env` (`API_KEY` and
`MUMA_API_KEY`) and in every consumer configured with it -- the LMS integration's
`LMS_MUSIC_MANAGEMENT_API_KEY`, the CI/CD variables, and any deployed
`docker-compose` environment -- before the old value can be considered dead.
