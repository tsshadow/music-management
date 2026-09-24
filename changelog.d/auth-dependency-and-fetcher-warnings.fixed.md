- **Every router checks the API key through the one shared dependency.** Eleven routers carried a
  `verify_api_key` of their own -- once copies that answered a database outage with
  `401 Invalid API key`, lately thin wrappers where such a copy could return. They now all import
  `routers.users.verify_api_key`, and a test fails if a router defines one again. Answers are
  unchanged: unknown key `401`, disabled account `403`, outage `503`. The routers' own "no database
  connection" checks now answer `503` with `Retry-After` instead of `500`. Bug report 065.
- **A missing image-provider credential is reported once per process.** Every single-artist portrait
  fetch built a new fetcher, which logged the missing Spotify credentials and Last.fm key as
  `WARNING`s and "no configured image provider" as an `ERROR` again -- each one an alert push. They
  are now logged at full level once, then at `DEBUG`. Bug report 065.

<!-- release notes -->

- **Fetching a single artist's portrait no longer sends a "credentials missing" alert every time.**
