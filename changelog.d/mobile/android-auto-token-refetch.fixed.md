- **Android Auto kept failing with "wrong username or password" after an administrator replaced the
  listener's Subsonic token.** The app only fetched the new token when its screen opened, and in the
  car it never does. A request the server refuses with error 40 (or HTTP 401) now makes the app fetch
  the token once via its MuMa key and repeat the request -- for browsing, streaming and cover art.
  Concurrent refusals share one fetch, a token that still does not work backs off for five minutes
  instead of looping, and a fetch that finishes after a sign-out is dropped (issue #73, bug report
  111).

<!-- release notes -->

- **Android Auto picks up a replaced login token by itself.** Before, it kept failing with "wrong
  username or password" until the app was opened on the phone.
