# title: Ultrasonic welcome-screen Google Sign-In fails with a network error

# status: fixed

# reported problem
Tapping "Sign in with Google" on the very first login screen (the welcome dialog shown on a
fresh Ultrasonic install) always fails with "Er is een netwerkfout opgetreden. Controleer het
server adres en probeer het later opnieuw." ("A network error occurred. Check the server address
and try again later."), even though the same Google Sign-In flow works fine once a server has
already been configured (e.g. from the server-edit screen).

# Possible reason
`SubsonicAPIClient` (and its `mumaApi` used for the `/api/auth/google` call) is a Koin singleton,
lazily built once from whatever `ActiveServerProvider.getActiveServer()` returns at the time of
first injection. On a fresh install, before the welcome dialog's "OK"/Google button has ever
successfully set an active server, `getActiveServer()` falls back to the offline pseudo-server
(base URL `http://localhost`). `NavigationActivity.performWelcomeGoogleSignIn()` reused this
same injected `subsonicAPIClient.mumaApi`, so the Google auth request was silently sent to
`http://localhost/muma` instead of the real production Muma backend, always failing and
surfacing as the generic network-error toast/message.

# solution
`performWelcomeGoogleSignIn()` now builds a dedicated `MumaAPIClient` targeting the fixed,
known-good production server address (`ServerSettingsModel.STATIC_SERVERS[0].url`) instead of
reusing the shared, potentially-stale `subsonicAPIClient.mumaApi`. The Muma base-URL derivation
logic (including the `example.com` -> `https://muma.example.com` special case) was
extracted from `SubsonicAPIClient.mumaApi` into a reusable `SubsonicAPIClient.mumaBaseUrlFor()`
companion function so both call sites stay consistent.
