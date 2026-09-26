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
| A listener who signed in on an older app version updates the app | The first time the app opens, it quietly picks up the listener's token. Until then it keeps working the old way. |
| Android Auto starts before the app's screen was ever opened after an update | Playback works (old way) until the app's screen is opened once. |
| The listener has no token yet | One is created for them the first time they sign in. |
| An administrator already gave the listener a token | The apps use that same token; external players keep working. |
| An administrator replaces the listener's token | The web player asks the listener to sign in again; the phone picks the new token up the next time the app opens. |
| The music server cannot hand out a token (e.g. an older server) | Everything keeps working the old way. |
| A listener signs out | The token is forgotten on that device along with the password. |

## Acceptance Criteria

1. After signing in, no request from the Android app or the web player to the music server carries
   the password in its address.
2. Streaming, cover art, artist images, search, lists and Android Auto keep working.
3. A listener without a token gets one automatically; a token an administrator already issued is
   reused and keeps working for external players.
4. A listener can only ever obtain their own token, never anyone else's.
5. Diagnostics reports and exported crash logs never contain the token or the password.
6. If the token cannot be obtained, the apps keep working as before.

## Open Questions / Not Yet Decided

- Whether the password fallback should be removed once every installed app has fetched a token.
  Deferred: tracked as a follow-up issue, decided after a release cycle.
- The phone only re-reads a replaced token when the app's screen opens; Android Auto alone does not
  notice until then. Accepted for now (administrators rarely replace tokens), tracked as a
  follow-up issue.
