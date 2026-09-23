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
  Only rejected attempts count, and a login is counted per account rather than
  per client address: LMS re-checks the password here on every Subsonic request
  over a hop that carries no client address, so counting successes under one
  shared key logged the whole installation out. Spraying one password across
  many accounts is covered a layer up, by LMS's own per-client `LoginThrottler`.
* Passwords are stored as bcrypt hashes. Revoking sessions clears the api_key
  and every refresh token in one step.

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

What `services/muma-mobile` does with credentials, since bug report 037:

* **TLS is verified.** The one server the app signs in to has a publicly trusted
  certificate, and `StaticServers.ALLOW_SELF_SIGNED_CERTIFICATE` is `false`, so
  the Subsonic client uses the system trust store. `network_security_config.xml`
  refuses cleartext except to `localhost` (the Capacitor WebView's own origin)
  and trusts user-installed CAs only in debuggable builds.
* **The Subsonic password is still sent as `p=enc:<hex>`.** LMS accepts the
  salted `t`/`s` form only for the per-user Subsonic token, not for the login
  password the app holds, so switching would lock every account out. Open work
  records the way out; until then the password is protected by TLS and by log
  redaction, not by the encoding, which is reversible.
* **Logs are redacted before they leave the phone.** `LogRedaction` masks the
  `u`/`p`/`t`/`s`/`apiKey` query parameters, credential headers and
  credential-named settings in every ring-buffer line, which is what diagnostics
  reports upload. The debug build's OkHttp logging redacts the same names.
* **Exported content providers serve only their own files.** The album-art
  provider must stay exported for Android Auto, the media notification and the
  widget, so it refuses any key that could resolve outside the art cache.
* **No hoster credential is compiled in.** The update check asks apk-hoster as
  its public read-only `guest` account; the upload password lives only in CI.
* **WebView remote debugging is debug-only** (Capacitor's default when the key
  is absent from `capacitor.config.json`).

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

### Rotating a leaked secret

Removing a committed secret from the working tree does not unpublish it -- every
clone still holds it, and `git log -S'<the value>'` finds it in seconds. Deletion
is the second step; the first is always to rotate the credential at its source,
after which the copy in history is worthless.

The system API key described above is in this position. It was committed until
the `api_key.py` change, so it must be replaced in `.env` (`API_KEY` and
`MUMA_API_KEY`) and in every consumer configured with it -- the LMS integration's
`LMS_MUSIC_MANAGEMENT_API_KEY`, the CI/CD variables, and any deployed
`docker-compose` environment -- before the old value can be considered dead.
