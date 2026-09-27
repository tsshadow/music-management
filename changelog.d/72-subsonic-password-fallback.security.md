- **The web player never signs a Subsonic request with the password any more** (issue #72). Since
  bug report 103 it signed with the per-user Subsonic token, but fell back to `p=<password>` in
  plain text whenever no token was stored for the signed-in name -- and on production that was the
  normal case, not a transition: in the reverse proxy's access log for 2026-09-27 02:51-04:26 UTC,
  all 664 `/rest` requests from the web shell carried `p=` and none a `t=`, while all 336 native
  requests were token-signed. `authParams` is now the token query or empty; a missing token is
  fetched once before the first request (at start-up and in the Android shell's boot, which first
  takes over the native client's token), a token issued for a case variant of the name now adopts
  LMS's spelling instead of never signing, and a sign-in without a MuMa session or a token fails
  instead of pinging with the password. While no token can be had nothing Subsonic is requested
  and a notice says "De server geeft geen toegang" (with a retry) or "Log opnieuw in" instead of
  showing an empty library. The stored password now only re-obtains a refused MuMa key and marks
  the session as signed in.
<!-- release notes -->
- The web player no longer puts your password in any web address, not even before it has fetched
  its sign-in token. If the token cannot be fetched you now see "server not reachable" or "sign in
  again" instead of an empty library.
