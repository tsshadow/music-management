# The App Trusts Any Certificate And Leaks Its Secrets

# status: fixed — certificate checks on, cleartext limited to localhost, provider confined to the art cache, no upload password in the APK, WebView debugging debug-only, credentials redacted from logs; password mode deliberately unchanged (see solution)

# reported problem
A security review of `services/muma-mobile` found six defects, all confirmed by reading the code:

1. `StaticServers` set `allowSelfSignedCertificate = true` for the production server, which has a
   publicly trusted certificate. That flag makes `SubsonicAPIClient` install a trust-all
   `X509TrustManager` and a hostname verifier that returns `true` for every host, so anyone on the
   network path (a hostile Wi-Fi, a compromised router) could present any certificate, read every
   request and collect the password. `network_security_config.xml` also allowed cleartext to every
   host and trusted user-installed CAs in the release build.
2. `forcePlainTextPassword = true` on the same server sends the password on every request as
   `p=enc:<hex>` — a reversible encoding, not a hash — in the URL, and therefore in any access log
   along the way.
3. `AlbumArtContentProvider` is exported without a permission and appended the cache key from the
   URI to the album-art directory unchecked. Any app on the phone could open
   `content://nl.teunschriks.mumamobile.provider.AlbumArtContentProvider/x|../../shared_prefs/nl.teunschriks.mumamobile_preferences.xml`
   and read the preferences file, which holds `staticPassword` and `mumaApiKey` in plain text.
4. `app/build.gradle` compiled `APK_HOSTER_PASSWORD` — the apk-hoster *upload* password — into
   `BuildConfig`, and `AppUpdate.fetchLatest` sent it as `X-Upload-Password` on every update
   check. Anyone who unpacks the APK holds the credential that publishes an APK to every phone.
5. `assets/capacitor.config.json` set `android.webContentsDebuggingEnabled: true`, which enables
   Chrome remote debugging of the WebView — and with it the session, the stored credentials and
   the muma API key — in release builds.
6. Credentials reached logs that leave the phone. `RingBufferLoggerTree` keeps every line at DEBUG
   and above in release and is uploaded with every diagnostics report; `CachedDataSource.open`
   logged the full `DataSpec` (the stream URL with `u=` and `p=`) at INFO; the debug build's
   OkHttp logging at `HEADERS` level printed `X-API-Key` and the `p`/`t`/`s` query parameters.

# Possible reason
- The server settings are inherited from Ultrasonic, where both flags are per-server user choices
  for self-hosted Subsonic servers behind self-signed certificates or LDAP. When the server list
  became one hard-coded entry the flags were set to whatever made the first connection work and
  never revisited. The network config is the same inheritance: permissive so any user-entered
  server works.
- The provider was written for Android Auto and trusted that only the app builds its URIs.
- The update check was ported from the legacy `UpdateChecker`, which had always sent the password
  header; nobody checked what apk-hoster actually requires for `/api/version`.
- `webContentsDebuggingEnabled` was set while bringing up the Capacitor shell and left in.
- Bug report 036 masked the settings dump, but only `key: value` pairs; URLs and headers were not
  covered.

# solution
1. `StaticServers.ALLOW_SELF_SIGNED_CERTIFICATE = false`; the client now uses the system trust
   store. `network_security_config.xml` refuses cleartext except to `localhost`/`127.0.0.1` (the
   Capacitor WebView origin and the offline placeholder URL) and trusts only system CAs; user CAs
   are trusted in debuggable builds only, through `debug-overrides`. The redundant
   `android:usesCleartextTraffic="true"` is gone from the manifest.
2. **Deliberately unchanged, and why.** The salted form (`t=md5(password+salt)&s=salt`) is not
   accepted by LMS for a login password: `SubsonicResource::authenticateUser` checks a `t`/`s` pair
   against the user's *Subsonic API token* (`db::AuthToken`, domain `subsonic`), and verifies `p`
   through the music-manager password service. LMS never holds the login password in a form it
   could salt and hash, so switching the app to token auth would reject every account with "wrong
   username or password". `forcePlainTextPassword` stays `true`, now as the documented constant
   `StaticServers.FORCE_PLAIN_TEXT_PASSWORD`, pinned by `StaticServersTest`. What changes is its
   exposure: the password only travels over verified TLS (item 1) and is redacted from every log
   the app writes (item 6). Removing it from the URL needs the app to obtain the per-user Subsonic
   token first; that is recorded in `docs/open-work.md`.
3. `AlbumArtPath.resolve` refuses a key containing `/`, `\`, `..` or NUL and checks that the
   canonical path is strictly inside the canonical album-art directory; `openFile` returns null
   otherwise, before the key is used for a download or an open. The provider stays exported: its
   readers are Android Auto, the system media notification (both read `MediaMetadata.artworkUri`)
   and the launcher drawing the widget's `RemoteViews.setImageViewUri`, all in other processes,
   and none of those paths hands out a URI grant the app could scope. It now serves nothing but
   files in the art cache.
4. The update check asks apk-hoster as its public read-only `guest` account
   (`/api/version?apk=<series>&u=guest&p=guest`), the same account the download link already used;
   `guest` has `view,download`, and `view` is all `/api/version` requires (verified against the
   apk-hoster source and with a GET against the live instance: 200 for both series with guest,
   401 without credentials). `APK_HOST_PASSWORD` and the unused `APK_HOST_USER` are removed from
   `BuildConfig`. `APK_HOSTER_PASSWORD` is still passed to the CI build container, where only
   `scripts/deploy.sh` reads it for the upload. Every APK published before this fix carries the
   password, so it must be rotated — see `docs/open-work.md`.
5. The key is removed from `capacitor.config.json`; Capacitor then enables WebView debugging only
   when the app is debuggable, i.e. in the debug build.
6. `LogRedaction.redact` now also masks the `u`, `p`, `t`, `s` and `apiKey` query parameters and
   the `X-API-Key`, `Authorization` and `X-Upload-Password` headers. `RingBufferLoggerTree` runs it
   over every line before keeping it, `CachedDataSource` logs the `DataSpec` through
   `LogRedaction.redactUrl`, and both OkHttp logging interceptors come from
   `SubsonicAPIClient.redactingLoggingInterceptor`, which applies OkHttp's own `redactHeader` and
   `redactQueryParams` for the same names.

Tests: `AlbumArtPathTest`, `LogRedactionTest` (extended), `StaticServersTest`, `AppUpdateTest`
(updated) and `RedactingLoggingInterceptorTest` in `:core:subsonic-api`.
