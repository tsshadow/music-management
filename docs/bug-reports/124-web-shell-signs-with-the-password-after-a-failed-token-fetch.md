# The web shell signed with the password for hours after one failed token fetch

# status: fixed

# reported problem

After bug report 103 (MR !1034) the web player and the app's web shell sign Subsonic requests with
the per-user Subsonic token. On production they did not. The `lms-reverse-proxy` access log for
2026-09-27 showed Teun's Pixel sending every web-shell request (`c=spotify`, WebView user agent,
referer `http://localhost`) with a plain `p=<password>`: 664 requests between 02:51 and 04:26 UTC
and 536 between 04:38 and 05:17:18 UTC, none with `t=`. The native client on the same phone
(`c=Ultrasonic`) signed all of its requests with the token over the same time.

Ruled out, read-only against production:

- **The account.** MuMa's user 1 is `user` and LMS's user 1 is `user` with `muma_id` 1, and LMS
  holds exactly one `subsonic` `auth_token` row, for that user. `u=` was `user` on every request
  from both clients. A token stored under a different spelling of the name would not have signed,
  but there was no different spelling.
- **An old web bundle.** The APK the phone ran from 2026-09-26 18:02 (7.6.0, bundle `3804b1347f`,
  per apk-hoster's download log) already contains `GET /api/auth/subsonic-token` and the same
  `authParams`/`restoreSession` logic as develop.

# Possible reason

The web code signs correctly *once a token is stored*. Two things decide whether one is:

1. **It was fetched once per page load, and a failed fetch was silent.** `restoreSession` (shell)
   and `hydrateMumaUserFromApiKey` (start-up) each asked once. `refreshSubsonicToken` returned
   `null` on any failure, and nothing asked again until the next page load. Until then `authParams`
   fell back to `p=`. The Android WebView keeps a page alive for hours, and production restarts
   music-manager on every deploy (seven releases between 19:49 and 02:53 that night, and again at
   04:36).
2. **The first requests of a start without a token went out before the fetch.** The admin check,
   the sidebar's genres and labels and the ping all fire as soon as credentials exist, and so were
   signed with `p=` even when the fetch then succeeded.

The production timeline fits (1) and nothing else found:

- music-manager restarted at 04:36:01.
- From then until 05:17:18 no request for the token reached it at all, while the web shell sent
  536 `p=` requests. The page was alive and never asked again.
- The phone downloaded APK 7.8.1 at 05:11:53 (apk-hoster log), and the app restarted. At 05:17:18
  three token fetches arrived, all answered 200 (native refresher, `hydrateMumaUserFromApiKey`,
  `restoreSession`). The first web-shell `t=` request is logged in that same second, and every
  later one is token-signed (1,096 by 05:46).
- The same restart with a working fetch fixed it at once. The earlier page had no token, and
  nothing in it ever asked again.

The logs from before 04:36 are gone with the restart, so the exact failed fetch of the earlier page
is not visible. The browser test below reproduces the mechanism on the real test stack against
develop:

- **A start without a stored token.** Develop sends `getUser`, `getGenres` ×2, `getRecordLabels`
  and `ping` with `p=` before its token fetch.
- **A start whose token fetch fails.** Develop sends all five with `p=` and never asks again.

A fresh sign-in and a start with a stored token sign everything with `t`/`s` on develop too.

Found on the way: the search dropdown's thumbnails (`SearchResults.svelte`) built
`/rest/getCoverArt` URLs with no credentials at all, so they were never authenticated.

# solution

Issue #72, MR !1089.

- **Fail closed.** `authParams` is the token query or empty. `subsonicJson` fetches a missing token
  before the call and, when none comes, throws `SubsonicTokenUnavailableError` without sending
  anything. An unsigned call would be answered with error 40 and end the session.
- **Keep asking.** `keepSubsonicTokenFresh` (started in `App.svelte`) retries every 30 s, when the
  page becomes visible and when the device comes back online, for as long as a name is signed in
  and no token signs for it. `ensureSubsonicToken` shares one fetch between callers.
- **Sign-in.** The token is asked for up to three times on a busy or 404 answer. A refusal is final
  at once.
- **What the user sees.** While no token can be had, a notice says why ("De server geeft geen
  toegang" with a retry, or "Log opnieuw in").
- **Shell handover.** The shell takes over the native client's token from the bridge at start.
- **Thumbnails.** The search thumbnails are signed.
- **Proof.** `services/frontend/tests/browser/subsonic-signing.spec.js` signs in through the UI
  against `docker/compose.test.yml` and asserts that every `/rest` request (API, cover art,
  stream) carries `t` and `s` and none carries `p`. It covers four starts: a fresh sign-in, a start
  with the stored session, a start without a stored token, and a start whose token fetch fails.
  It fails on develop (the last two send `p=`) and passes on the branch.
