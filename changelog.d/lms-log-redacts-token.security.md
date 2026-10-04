- **The LMS request log printed the token and salt of a Subsonic request.** Its parameter list
  replaced only `p`, `password` and `apiKey` with `*REDACTED*`, so every logged request showed `t`
  and `s`. A failed request is logged at `ERROR`, which production keeps. A signed `getCoverArt`
  URL that the app sent as an `id` also put the user name, token and salt in the line. LMS now
  redacts `t` and `s`, and the `u`, `t`, `s`, `p` and `apiKey` values in a parameter value that is
  a URL itself, also when it is percent-encoded (bug report 150).

<!-- release notes -->

- The server log no longer shows the login token of a request.
