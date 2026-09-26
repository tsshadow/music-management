- **The app stopped sending its password as `p=enc:<hex>` in every Subsonic URL.**
  `StaticServers.FORCE_PLAIN_TEXT_PASSWORD` was `true`, so every stream, cover and API request
  carried the password in a reversible encoding (bug report 054, item 2). The app now fetches the
  user's own Subsonic token from `GET /api/auth/subsonic-token` after every sign-in and on every
  start, keeps it in the encrypted settings next to the MuMa tokens, and signs each request with
  `t=md5(token + salt)&s=salt`, a fresh salt each time; the flag is `false`. Until the first fetch
  succeeds -- an upgraded install, or Android Auto running before the app was opened -- the old
  form remains the fallback, so playback never stops over it. The crash report saved to Downloads
  is now redacted like the uploaded one, and diagnostics also mask credential fields in JSON.
  Bug report 103, closes GitLab issue #21.

<!-- release notes -->

- **Je wachtwoord gaat niet meer mee in elk verzoek aan de muziekserver.** De app haalt na het
  inloggen een eigen token op en ondertekent elk nummer, elke hoes en elke lijst daarmee. Je merkt
  er niets van: inloggen, afspelen en Android Auto werken zoals altijd.
