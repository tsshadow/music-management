# First-Run Server Screen: Technical Design

Implements [functional.md](functional.md). Issue #192. Builds on #189 step 6
([public-edition/technical.md](../public-edition/technical.md), MR "server URL and Google client id
from build settings") and on the start-up check of
[app-start-reachability](../app-start-reachability/technical.md).

## Where It Starts

- `StaticServers.SERVER_URL` is `BuildConfig.MUMA_SERVER_URL`, read once when the object loads.
  `STATIC_SERVERS` is a `val` list built from it, so the address is fixed for the life of the
  process and for the life of the build.
- `ActiveServerProvider.getActiveServer()` and `signInServer()` copy that list's one entry.
  `MumaSystemPlugin.serverUrl()` derives `{subsonic, mumaApi}` from `signInServer().url` through
  `serverUrlsOf`, and `MusicServiceModule` builds `SubsonicClientConfiguration` from the active
  server. `resetMusicService()` reloads that Koin module, so a new address reaches the native client
  once the module is rebuilt.
- `SubsonicAPIClient.mumaBaseUrlFor(server, ownServerUrl, mumaApiUrl, ownDomain)` derives the MuMa
  base: the build's `muma.apiUrl` when the server is the build's own host or on `muma.ownDomain`,
  else `<server>/muma`. The web calls go to `<mumaApi>/api/...` and `<mumaApi>/health`.
- The shell's login page (`LoginPage.svelte`) already has a server field. It changes only the web's
  `credentials.url`. `mumaApiUrl` keeps the old value, and `saveCredentials` ignores `url`, so the
  native side keeps the build's address. The field is half a feature, and this design replaces it.
- The release build refuses to build without a real `MUMA_SERVER_URL` and `MUMA_GOOGLE_CLIENT_ID`
  (`checkMumaReleaseConfig`).

## Data Model

No server-side change. One new client setting:

| Key | Store | Value |
|---|---|---|
| `setting_key_server_url` (`Settings.serverUrl`) | default `SharedPreferences`, as `staticUserName` | the normalized server address, `""` while none is set |

It is not a secret, so it is not in `SecureSettings`. `backup_rules.xml` already includes the
default preferences in cloud backup and device transfer, so a restored install knows its server and
only has to sign in again (the credentials are excluded, issue #115). The settings blob the app
syncs to music-manager (`/api/users/{id}/settings/ultrasonic`) does not get this key: it is stored
on the server it names, so it can never help to find that server.

### `ServerAddress`

A new object, `data/ServerAddress.kt`, is the one reader and writer of the address:

- `current(): String?` reads `Settings.serverUrl`, `null` when empty.
- `normalize(input): Result` is pure, for the tests. It trims the input, adds `https://` when no
  scheme is given, lower-cases scheme and host, and strips a trailing slash. A path stays, for a
  server behind a prefix such as `https://example.org/lms`. It refuses, each with its own reason:
  an empty input, a scheme other than `https` (`insecure` for `http`), a missing host, user info
  (`user:pass@host`), a query or a fragment. The host check reuses `ServerHosts.hostOf`.
- `store(url)` writes the normalized address, then calls `ActiveServerProvider.invalidateCache()`
  and `resetMusicService()` on the main thread.
- `isBuildServer(url)` is `ServerHosts.isOwn(url, BuildConfig.MUMA_SERVER_URL, BuildConfig.MUMA_OWN_DOMAIN)`.

### Run-time reading instead of `BuildConfig`

| Now | After |
|---|---|
| `StaticServers.SERVER_URL` (`val`) | `StaticServers.BUILD_SERVER_URL` keeps the build value and is used only as `ownServerUrl` (the reference for `muma.apiUrl`) and as the first-run prefill. `StaticServers.serverUrl()` returns `ServerAddress.current()`. |
| `StaticServers.STATIC_SERVERS` (`val`) | `StaticServers.servers()`: the same one-entry list, built from `serverUrl()` on each call, or an empty list while no address is set. `ActiveServerProvider` caches the result as it caches the server now. |
| `signInServer()` returns `STATIC_SERVERS.first()` | Returns `ServerSetting?`, `null` without an address. The callers (`saveSession`, `MumaSystemPlugin.serverUrl`) handle `null`. |
| `getActiveServer()` falls back to Offline when the id is not in the list | Unchanged. Without an address the list is empty, so the active server is Offline, which is what a fresh install has today. |
| `MusicServiceModule`: `ownServerUrl = StaticServers.SERVER_URL` | `ownServerUrl = StaticServers.BUILD_SERVER_URL`. The base URL already comes from the active server. |
| `serverUrlsOf(..., ownServerUrl = StaticServers.SERVER_URL)` | `ownServerUrl = StaticServers.BUILD_SERVER_URL`. |

The MuMa base stays derived: `mumaBaseUrlFor(server, BUILD_SERVER_URL, MUMA_API_URL, MUMA_OWN_DOMAIN)`.
For any server that is not the build's own host this is `<server>/muma`, which is the decided rule.
For the owner's APK nothing changes: its own host still gets `muma.apiUrl`. There is no field for
the MuMa host.

### An existing install

`ServerAddressMigration.run(store)` runs once per process from `UApp.onCreate`, next to
`migrateLegacyCredentials`, and before anything reads the address. When no address is stored and
the install was used before, it stores `BuildConfig.MUMA_SERVER_URL`. "Used before" means any of:
`Settings.signedIn`, a non-empty `Settings.staticUserName`, or `Settings.activeServer` not `-1`.
It never stores the example default `https://music.example.org`. An install that was built with the
default could never reach a server, so it gets the first-run screen like a fresh install.

The result for the owner's household: the update writes the address they already used, the
`ServerSetting` id stays `0`, the Room cache `…-meta-0` stays, and the session stays. No screen.

## The Check

A new native probe, `capacitor/ServerAddressProbe.kt`, runs on an IO dispatcher with its own
`OkHttpClient`: 8 s call timeout, no redirects to another host, the app's network security config.
It runs natively, and not as a `fetch` in the WebView, because the WebView's origin is
`http://localhost` and a cross-origin `fetch` to a server without CORS headers for it fails before
the answer can be read.

Two requests, in parallel, against the normalized address:

1. `GET <server>/rest/ping.view?f=json&c=<client id>&v=<protocol>` without credentials. A MuMa (LMS)
   server answers with a `subsonic-response` envelope: status `failed`, code 10 (parameter missing)
   or 40. Any envelope proves a Subsonic server.
2. `GET <mumaApi>/health`, where `mumaApi` is the derived base. music-manager answers JSON with
   `"service": "music-manager"`, with 200 or with 503 (unhealthy, still there).

| Result | `state` |
|---|---|
| `normalize` refused it | `invalid` or `insecure` |
| No network (`ConnectivityManager`, as `checkServer`) | `noNetwork` |
| Timeout, connection refused, unknown host | `unreachable` |
| `SSLHandshakeException`, `SSLPeerUnverifiedException` | `certificate` |
| Ping answered without an envelope (HTML, a captive portal, another server) | `notMuma` |
| Envelope, and `/health` names music-manager | `ok` |
| Envelope, and `/health` failed or named something else | `mumaUnreachable` |

`ServerAddressProbe.classify(network, pingOutcome, healthOutcome)` is a pure function, so every row
has a JVM test. It does not reuse `ServerReachability.classify`: that one answers "can I use the
server I am signed in to", with credentials. This one answers "is this a MuMa server", without any.

## API Contract

No HTTP endpoint changes. The contract that changes is the Capacitor bridge, `platform.system`
(`services/frontend/src/lib/platform/index.js` typedef, `MumaSystemPlugin.kt`,
`platform/capacitor/system.js`, `platform/browser/system.js`):

| Call | Request | Response | Error cases |
|---|---|---|---|
| `serverUrl()` / `loadServerUrl()` | none | `{subsonic, mumaApi, configured}`. `configured: false` with both strings empty while no address is stored. | none |
| `checkServerAddress` (new) | `{url}` | `{state, url, subsonic, mumaApi, buildServer}`. `url` is the normalized address (empty when `invalid`), `buildServer` is `ServerAddress.isBuildServer(url)`. | Never rejects on a failed check. Rejects only when the bridge call itself fails. |
| `setServerAddress` (new) | `{url, signOut}` | `{subsonic, mumaApi, configured: true}` | Rejects with `invalid` or `insecure` when `normalize` refuses `url`. It does not probe again: the page probed first. |
| `suggestedServerAddress` (new) | none | `{url}`: `BuildConfig.MUMA_SERVER_URL`, or `""` for the example default. | none |
| `googleSignInAvailable` | none | `{available}`: now also false when the stored address is not the build's own server. | none |

`setServerAddress` with `signOut: true` runs `SessionSignOut` (clears the session and the queue on the
main thread, as `signOut()` does), then `ActiveServerProvider.deleteMetaDatabase(0)` (the Room cache
of the old server; it is keyed by server id, and the id stays `0`), then `ServerAddress.store`.
Downloaded files stay. With `signOut: false` it only stores. The page passes `signOut: false` when
the new address has the same host and path as the old one, so a spelling change keeps the session.

The browser implementation: `serverUrl()` keeps answering from `window.location` with
`configured: true`; the three new calls are never made outside the shell, and answer
`{state: "ok"}`, reject and `{url: ""}`.

Not a breaking change for any other app. The web bundle is baked into the APK (the APK has to be
bumped for a frontend change to reach phones), so a bundle never meets a shell older than itself.

## The Web Side

- `bootstrapShell` (`nativeSession.js`): after `applyServerUrls`, when `configured` is false it does
  not start `checkServer` (there is nothing to ping) and returns
  `{native: true, signedIn: false, needsServer: true, ...}`. The start-up reachability check runs only
  for a configured server, so a fresh install never sees "Server niet bereikbaar".
- `App.svelte` (the shell branch that shows `LoginPage` today) shows `FirstRunServer.svelte` while
  `needsServer` holds. On success it calls `setServerAddress`, then `applyServerUrls` again, and
  shows `LoginPage`.
- `FirstRunServer.svelte`: the MuMa mark, a title, one `type="url"` field prefilled with
  `suggestedServerAddress()` on a first run (or the current address when opened to change it), the
  "Verbinden" button, and one message line per `state`. `mumaUnreachable` adds "Toch doorgaan" (open
  question in functional.md). While a check runs the button shows the existing button spinner and
  the field is disabled.
- `LoginPage.svelte`: in the shell, the editable server field and `applyServer()` go. In their place
  one line with the server's host and a "Wijzigen" link to `FirstRunServer`. `saveCredentials` stops
  sending `url`.
- `DeviceSettings.svelte`: a "Server" row at the top of the Apparaat tab with the address and
  "Wijzigen". It opens `FirstRunServer` in change mode. After a successful check of a different
  server, the confirmation dialog (`Modal.svelte`, "Confirmation dialog" in the style guide) asks
  before `setServerAddress({signOut: true})`. On yes the app resets its web session the way logout
  does (`signedOut`, stores cleared) and shows the login page.
- `About.svelte` reads `serverUrl()` as now.
- i18n: new keys under `firstRun.*` and `settings.device.server*` in every locale file, Dutch and
  English written, the others falling back to English as the i18n design allows.

## Google Sign-In

`GoogleSignIn.signIn` asks Credential Manager for a token for `BuildConfig.GOOGLE_WEB_CLIENT_ID`.
music-manager checks the token with `audience=GOOGLE_CLIENT_ID` (`routers/user_requests.py`), its
own single client id. A token for the owner's client id is therefore refused by any other server,
and that server's client id cannot be used either: the Android OAuth client that lets this APK ask
for a token is registered with the APK's signing certificate in the owner's Google Cloud project.

So `googleSignInAvailable` answers true only when a client id is compiled in and
`ServerAddress.isBuildServer(current)` holds. The login page already hides the button on false. A
public build has no client id and never shows it. Letting music-manager accept a list of audiences
is the follow-up named in functional.md.

## Build Settings

`muma.serverUrl` stops being the address and becomes the suggestion for a fresh install plus the
reference for `muma.apiUrl`. The build keeps reading it. `checkMumaReleaseConfig` stays as it is: it
guards the owner's release pipeline against shipping an APK with the example host and no Google
button, and a public build sets `muma.allowDefaults=true`. `services/muma-mobile/README.md` and the
#189 changelog text about "a build without them uses `https://music.example.org`" get updated: such a
build now asks.

## Style Guide (Rule 15)

Before the screen is built, `docs/styleguide.md` gets two entries in the Design Backlog as
**Pending**, and they move under Components when done:

- **First-run server screen** (app only): the login page's layout and its fixed `brand-green` accent
  (the login page is the one deliberate exception to the brand token, Brand token section), the
  field in the Forms & Inputs style, "Verbinden" as the primary pill, "Toch doorgaan" and "Opnieuw
  proberen" as secondary pills, and a refusal in the login page's existing error box
  (`bg-[#e91429]`), a check in progress in muted text.
- **Server line on the login page**: the host in muted `text-xs` with "Wijzigen" as a text link,
  replacing the server field.

The settings row and the change dialog use existing patterns (the Apparaat rows and the
Confirmation dialog) and need no new entry.

## Cross-App Impact

- MuMa Mobile (Kotlin): `ServerAddress`, `ServerAddressMigration`, `ServerAddressProbe`,
  `StaticServers`, `ActiveServerProvider`, `MusicServiceModule`, `ServerUrls.kt`,
  `MumaSystemPlugin`, `Settings`, `UApp`.
- Frontend (the bundle the shell serves): `FirstRunServer.svelte`, `App.svelte`, `LoginPage.svelte`,
  `DeviceSettings.svelte`, `nativeSession.js`, the platform typedef and both implementations, the
  locale files. The browser build behaves as before.
- music-manager, LMS: none.
- CI: `scripts/test/muma-mobile-emulator-smoke-inner.sh` expects the first-run screen on a wiped
  install, with the field showing `SMOKE_EXPECTED_SERVER` (the build's address, or empty for the
  default build), where it now expects the login page's server field.
- Both changelogs: a mobile fragment (`changelog.d/mobile/`) and a root fragment for the bundle.
  The app's `versionCode` goes up in the same release.

## Technical Acceptance Criteria

1. `ServerAddressTest` (JVM): `normalize` adds `https://`, keeps a path, strips the trailing slash,
   lower-cases the host, and refuses empty, `http://`, `ftp://`, user info, a query, a fragment and a
   bare path. `isBuildServer` for the build host, a host on `muma.ownDomain`, and a stranger.
2. `ServerAddressMigrationTest`: a used install without an address gets the build address; a fresh
   install gets none; the example default is never stored; a stored address is never replaced; a
   second run changes nothing.
3. `ServerAddressProbeTest` (JVM, `MockWebServer`): one test per row of the classification table,
   including a captive-portal HTML answer, a 503 `/health` that still names music-manager (`ok`), a
   timeout, and a TLS failure.
4. `StaticServersTest` and a new `ActiveServerProviderTest`: without an address the list is empty, the
   active server is Offline and `signInServer()` is null; after `store`, `getActiveServer()` and
   `serverUrlsOf` return the new address and the MuMa base `<server>/muma`; the build's own host still
   gets `muma.apiUrl`.
5. `CapacitorContractTest`: `serverUrl` with and without an address; `checkServerAddress`,
   `setServerAddress` (with and without `signOut`; with it the meta database is deleted and the
   session cleared), `suggestedServerAddress`, and `googleSignInAvailable` false for a foreign server.
6. `services/frontend/tests/unit/nativeSession.test.js`: an unconfigured shell returns `needsServer`, never calls `checkServer`
   and never restores a session.
7. New `tests/unit/FirstRunServer.test.js`: prefill, each `state` message, "Toch doorgaan", the disabled field while
   checking, and that success calls `setServerAddress` and then `loadServerUrl`.
8. New `tests/unit/LoginPage.test.js`: in the shell there is no server field, the host line and "Wijzigen" are shown,
   and `saveCredentials` gets no `url`. In a browser nothing changed.
9. New `tests/unit/DeviceSettings.test.js`: the server row; a change to another server asks first and passes
   `signOut: true`; a spelling change passes `signOut: false` and does not ask.
10. The emulator smoke test reaches the first-run screen on a wiped install and finds the expected
    prefill.
11. `./scripts/test/android-unit.sh`, `muma-mobile-ktlint.sh`, `muma-mobile-detekt.sh`,
    `./scripts/test/frontend-unit.sh` pass.

## Related Docs

- [docs/designs/public-edition/technical.md](../public-edition/technical.md)
- [docs/designs/app-start-reachability/technical.md](../app-start-reachability/technical.md)
- [docs/designs/mobile-sign-out-and-google/](../mobile-sign-out-and-google/)
- [docs/styleguide.md](../../styleguide.md)
