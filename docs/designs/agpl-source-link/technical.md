# AGPL source link — Technical Design

> Functional design: [functional.md](functional.md).

## Components

- `services/common/config_store.py`: field `public_source_url` (env `PUBLIC_SOURCE_URL`, group
  General, default `https://github.com/OWNER/music-management`).
- `services/music_manager/main.py`: `GET /health` gets the field `source_url`. `_public_source_url()`
  returns the setting only when `urlsplit` finds scheme http or https (any case), a host and no user info (`https://a@evil.example`), else `""`; a failing store also gives `""`. The endpoint is
  unauthenticated, and the web UI already reads it for the MuMa version, so no new request and no new
  endpoint exist. The field is added to the `503` answer too.
- `services/frontend/src/lib/sourceLink.js` (`safeSourceUrl`, `fetchSourceUrl`) re-checks the value the way the server does (`new URL`: http or https, a host, no user info; `https:///path` is refused up front) before it becomes an `href` or reaches `openUrl`. `fetchSourceUrl` gives up after 5 s and, in the native shell with an empty API base, does not fetch a relative `/health` at all. `SourceCodeLink.svelte` is the small link on the login screen, where `/health` is public, so the offer reaches people before they sign in.
- `docker/docker-compose*.yml` pass `PUBLIC_SOURCE_URL` (default the placeholder); `.env.example` and `docs/self-hosting.md` list it.
- `services/frontend/src/lib/settings/About.svelte`: reads `source_url` from the same `/health` call and
  renders a Source code section with an anchor (`target="_blank"`, `rel="noopener noreferrer"`). In the
  native shell the click goes through `platform.system.openUrl`, like the other external links.
- Locales `en` and `nl` (`settings.about.sourceCode`, `sourceCodeBody`); `brabants` and `sallands` fall
  back to `nl`.

## API change

Additive: one new string field in the `/health` answer. No existing field changes, so no consumer needs
an update (rule 7). `docs/api-specification.md` lists it. The Android app has no native About screen: it
loads the bundled web UI, so `services/muma-mobile` has no code change and no Kotlin test.

## LMS

`services/music-management-server/src/lms/ui/admin/About.cpp` is the About window of the inherited Wt
interface. It shows the upstream LMS version and homepage. It is not changed: the Svelte player is the
interface this project serves, and a C++ change would need a server build for a screen listeners do not
use.

## Tests

- `services/music_manager/tests/test_health.py` (`SourceUrlHealthTest`): configured value, empty value,
  non-http value, default of the field.
- `services/frontend/tests/unit/aboutSettings.test.js`: link rendered, hidden when empty, opened through
  the shell in the app.
