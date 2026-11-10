# First-Run Server Screen: Functional Design

## Overview

The Android app talks to one server, and that server's address is fixed when the APK is built
(`muma.serverUrl`, issue #189 step 6). A build without the setting points at
`https://music.example.org`, and nobody can change it without a new build. That makes the app
useless to anyone who runs their own MuMa server, which is the point of the public edition.

A fresh install now opens with one question: what is the address of your server? The listener types
it, the app checks that a MuMa server answers there, and then shows the login page. The MuMa API
address is not asked. The app works it out from the server address, the same way it does today
(`<server>/muma`). The address can be changed later under Settings, and from the login page.

Teun decided the scope on 2026-11-10: the screen asks only the server address, the MuMa API host is
derived from it, and the address can be changed in the settings. Issue #192.

## User Stories

- As someone who runs their own MuMa server, I want to install the public APK and point it at my
  server, so that I do not have to build the app myself.
- As a listener who mistyped the address, I want to be told what is wrong before I try to sign in,
  so that "wrong password" and "wrong server" are not the same error.
- As a listener whose server moved to a new address, I want to change the address in the settings,
  so that I do not have to reinstall the app.
- As the owner, I want my own APK to keep working after the update without a new question, so that
  nobody in the household notices the change.
- As the owner, I want a fresh install of my own APK to suggest my server, so that setting up a new
  phone is one tap.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Fresh install of a build without a server address | The app opens on the server screen with an empty field. The login page comes after it. |
| Fresh install of a build that has a server address (the owner's APK) | The server screen opens with that address filled in. One tap on "Verbinden" checks it and goes on to the login page. |
| Update from a version that had the address built in | No server screen. The app keeps using the address it used before, and the listener stays signed in. |
| The listener types `music.example.net` | The app reads it as `https://music.example.net`. |
| The listener types an `http://` address | The screen says only `https` addresses work, and stays. Nothing is stored. |
| The listener types something that is not an address | The screen says so under the field, and stays. |
| No network | The screen says there is no network connection, with "Opnieuw proberen". |
| Nothing answers at the address, or it answers slowly (8 s) | The screen says the server does not answer and shows the address it tried. |
| Something answers, but it is not a music server | The screen says no MuMa server was found at that address. |
| The music server answers, but the MuMa part behind it does not | The screen says the server was found but MuMa does not answer, and offers "Toch doorgaan". |
| The certificate is not trusted | The screen says the connection is not secure. There is no way past this. |
| The check succeeds | The address is saved and the login page opens, with the server shown above the fields and a "Wijzigen" link. |
| On the login page, "Wijzigen" | Back to the server screen, with the current address filled in. |
| Settings, Apparaat, "Server" | Shows the current address with "Wijzigen". |
| Changing the address while signed in | After the check, a dialog asks "Andere server gebruiken?" and says what happens: you are signed out and the queue is cleared, downloads stay on the phone. On yes, the app switches and shows the login page. |
| Changing the address to the same server (only the spelling differs) | No sign-out. The address is saved as typed. |
| Sign in with Google | Offered only when the server is the one this APK was built for. Other servers sign in with a name and password. |
| Android Auto before a server is set | The car says to open MuMa on the phone first, as it does when signed out. |
| A browser | No change. The web player knows its server from the page address. |

## Acceptance Criteria

1. A fresh install of the public APK opens on the server screen, not on the login page.
2. Typing the address of a working MuMa server and tapping "Verbinden" leads to the login page, and
   signing in there works.
3. An `http://` address, a malformed address, an address where nothing answers, and an address with
   another kind of server each give their own message, and none of them is stored.
4. Updating the owner's APK from the previous version shows no server screen and keeps the listener
   signed in.
5. A fresh install of the owner's APK shows its server filled in.
6. Changing the server in the settings while signed in asks first, then signs out, clears the queue,
   keeps downloads, and shows the login page for the new server.
7. After a change of server, every request goes to the new server: the player, the MuMa pages, the
   car and downloads. Nothing is still sent to the old one.
8. The Google button is shown only for the server the APK was built for.
9. The web player in a browser looks and works as before.

## Open Questions / Not Yet Decided

- **"Toch doorgaan" when only MuMa does not answer.** Proposed: allow it, because LMS alone can
  still play music and the MuMa part may be restarting. The other choice is to refuse, as for a
  server that does not answer at all.
- **`http://` on a home network.** The app refuses cleartext to every host but `localhost`
  (bug report 054), so this design refuses `http://` addresses. Someone with a server on their LAN
  and no certificate cannot use the public APK. Proposed: keep it so.
- **Google sign-in for other servers.** A Google token is made for one OAuth client, and
  music-manager accepts tokens for its own client id only. A server run by someone else would need
  the APK's client id in its own configuration. Proposed: no Google for other servers in this
  change. A follow-up can let music-manager accept a list of client ids.
