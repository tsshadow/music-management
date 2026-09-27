- **The web player never signs a Subsonic request with the password any more** (issue #72, bug
  report 124). Since bug report 103 it signed with the per-user Subsonic token, but fell back to
  `p=<password>` in plain text whenever no token was stored. On production that was the normal
  case: the web shell sent 1,200 `/rest` requests with `p=` on 2026-09-27 while the native client
  signed all of its requests with the token.
  - **Cause.** The token was fetched once per page load and a failed fetch was never repeated. The
    phone's WebView page outlived the music-manager restart that made its fetch fail, and signed
    with the password until the app restarted at 05:17 -- in the same second its next fetch
    succeeded, it switched to `t=`.
  - **Fix.** `authParams` is now the token query or empty. A missing token is fetched before the
    first request and asked for again every 30 s, on returning to the page and on reconnecting. A
    sign-in retries a busy token endpoint and fails instead of pinging with the password.
    `subsonicJson` sends nothing unsigned.
  - **What you see.** While no token can be had a notice says "De server geeft geen toegang" (with
    a retry) or "Log opnieuw in" instead of showing an empty library.
  - **Also fixed.** The search thumbnails, which carried no credentials at all, are signed.
  - **Proof.** A Playwright test against the test stack asserts that no API, cover or stream
    request carries `p` across four starts: fresh sign-in, stored session, start without a token,
    and start whose token fetch fails.
  - **Password storage.** The stored password now only re-obtains a refused MuMa key and marks the
    session as signed in.
<!-- release notes -->
- The web player no longer puts your password in any web address, not even before it has fetched
  its sign-in token. If the token cannot be fetched you now see "server not reachable" or "sign in
  again" instead of an empty library.
