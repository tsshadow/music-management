# Subsonic Token Signing — Functional Design

## Overview

Every request the MuMa apps make to the music server -- each song that streams, each cover that
loads, each list that is fetched -- has to prove who is asking. Until now the Android app did that
by putting the listener's own login password in the web address of every request (lightly
disguised as `p=enc:<hex>`, which anyone can undo), and the web player put it there in plain text.
Web addresses end up in server access logs, proxy logs and browser history, so the password was
copied into all of them. This is item 2 of bug report 054, tracked as GitLab issue #21, and fixed
by bug report 103.

The music server already supports a safer way: each listener has a personal *Subsonic token*, and a
request proves the listener's identity with a one-off fingerprint of that token instead of the
password. This feature gives every signed-in listener their own token automatically and makes the
apps use it.

## User Stories

- As a listener, I want my password to never appear in a web address, so that it does not end up
  in logs or history I have no control over.
- As a listener, I want to notice nothing: signing in, playing, cover art and Android Auto work as
  before, without extra steps.
- As an administrator, I want tokens I hand out for external players to keep working, so that
  giving the apps their own tokens does not break anyone's setup.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| A listener signs in (phone or browser) | Signing in works as before. From then on, no request carries the password. |
| A listener who signed in on an older app version updates the app | Before the first song, cover or list is requested the app fetches the listener's token, quietly. The password is never sent in an address again, not even once (issue #72). |
| Android Auto starts before the app's screen was ever opened after an update | The token is fetched when the car starts the app, before the first browse or play. If that fails the car says "sign in again" or "server not reachable" instead of showing empty lists. |
| The token cannot be fetched (server down, or the account refused) | Nothing is requested from the music server. The phone's and the browser's screens say "the server is not reachable -- try again" or "sign in again", with a button for each; the car shows the same message. |
| The listener has no token yet | One is created for them the first time they sign in. |
| An administrator already gave the listener a token | The apps use that same token; external players keep working. |
| An administrator replaces the listener's token | The web player asks the listener to sign in again; the phone, Android Auto included, fetches the new token on the first request the server refuses and repeats that request, without the app's screen having to open (issue #73). |
| The music server cannot hand out a token (e.g. an older server) | Signing in fails with "no connection to the server"; there is no old way any more. |
| A listener signs out | The token and the MuMa key are forgotten on that device. |
| A listener signs in | The password is used for the sign-in and then forgotten; neither the phone nor the browser keeps it (issue #101). |
| A listener who signed in on an older app version updates the app (issue #101) | Nothing to do: they stay signed in, and the password the old version stored is removed. |
| The listener's account key is revoked or the account removed | The phone and the browser show the sign-in page (password or Google) instead of signing in again in the background; the car says "Sign in again in the MuMa app on your phone". |

## Acceptance Criteria

1. After signing in, no request from the Android app or the web player to the music server carries
   the password in its address.
2. Streaming, cover art, artist images, search, lists and Android Auto keep working.
3. A listener without a token gets one automatically; a token an administrator already issued is
   reused and keeps working for external players.
4. A listener can only ever obtain their own token, never anyone else's.
5. Diagnostics reports and exported crash logs never contain the token or the password.
6. If the token cannot be obtained, no request to the music server is sent, and the listener sees
   why ("sign in again" or "server not reachable") rather than an empty library (issue #72).
7. After signing in, the password is stored nowhere on the device -- not in the app's settings,
   not in the browser's or WebView's storage -- and updating from an older version removes a stored
   one without signing the listener out (issue #101).

## Open Questions / Not Yet Decided

- ~~Whether the password fallback should be removed once every installed app has fetched a
  token.~~ Decided (issue #72): removed. See the technical design, "Fallback decision".
- ~~The phone only re-reads a replaced token when the app's screen opens.~~ Resolved (issue #73,
  bug report 111): a refused token is fetched again and the request repeated once.
- ~~Whether the stored password can go once nothing signs with it.~~ Decided (issue #101): removed;
  a revoked key means signing in again. See the technical design, "No stored password".
