- **The app never puts the password in a Subsonic URL any more, not even before it has a token**
  (issue #72). Since bug report 103 the native client signed with the Subsonic token but fell back
  to `p=enc:<hex>` while none was stored, and the web shell to plain `p=` -- which on production
  was every one of its 664 requests in the measured window. The password interceptors
  (`PasswordHexInterceptor`, `ProxyPasswordInterceptor`) and the `FORCE_PLAIN_TEXT_PASSWORD` flag
  are gone; `TokenSigningInterceptor` signs with the stored token or, when none is stored, fetches
  one first (`SubsonicTokenRecoverer.obtain`, with a 30 s back-off after a failure), and otherwise
  throws `SubsonicTokenUnavailableException` without sending the request -- stream URLs included.
  The media session fetches a missing token as it starts, so an Android Auto cold start without
  the UI has one before its first browse; when none can be had the car shows "Sign in again in the
  MuMa app on your phone" or "Cannot reach the MuMa server" instead of empty lists. The bridge now
  hands the native token to the web shell, which signs with it instead of the password.
<!-- release notes -->
- The app no longer sends your password with any request to the music server, not even right after
  an update. If it cannot fetch its sign-in token, the app and the car say "sign in again" or
  "server not reachable" instead of showing empty lists.
