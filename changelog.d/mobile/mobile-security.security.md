- **The app accepted any certificate for the MuMa server.** It skipped certificate and hostname
  checks for a server that has a valid certificate, so anyone on the network path could pose as the
  server and read the password. It now uses the normal trust store, refuses unencrypted
  connections except to the phone itself, and trusts user-installed certificates only in the debug
  build (bug report 037).
- **Any app on the phone could read MuMa's stored password through the cover-art provider.** A
  cover-art address with `../` in it opened files outside the artwork cache, including the settings
  file with the password and the MuMa API key. Such addresses are now refused.
- **The APK contained the apk-hoster upload password.** The update check sent it; it now asks as
  the hoster's read-only guest account, and the password is no longer compiled in.
- **WebView remote debugging was on in the release app.** It is now limited to the debug build.
- **Stream URLs and request headers in the log carried credentials.** The username, the password,
  its token and salt, the API key and the `X-API-Key` header are masked before a line reaches the
  diagnostics log, and in the debug build's request logging.

<!-- release notes -->

- **Security fixes.** The app checks the server's certificate again, other apps can no longer read
  its stored password, and credentials are kept out of the diagnostics log and out of the APK.
