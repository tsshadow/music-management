# App start: server reachability and offline mode — Functional Design

## Overview

When the Android app starts, it used to go straight into restoring the play queue from the server.
With the server switched off, or the phone on a network that cannot reach it, that meant a boot screen
that waited, then a mini player with an empty or broken queue and lists that failed one by one. Nothing
said *why*, and there was no way to say "just play what is on the phone".

The app now asks the server once, before restoring the queue, whether it answers. When it does, the start
is the same as before. When it does not, the boot screen says so and offers three ways on: try again, wait
for the server, or continue offline with the music on the device. Requested by Teun; "Wachten op server"
was added to the original two options during review.

## User Stories

- As a listener starting the app while the home server is down, I want to be told the server is not
  reachable, so that I do not wait for a start that cannot finish.
- As a listener on a plane, I want to continue with my downloaded music, so that the app is useful without
  a connection.
- As a listener whose server is restarting, I want the app to wait and continue on its own when the server
  is back, so that I do not have to keep pressing "try again".
- As a listener in offline mode, I want to see how much of my queue could not be kept, and get the full
  queue back when the server returns, so that nothing is lost.
- As a listener whose password was changed, I want the login page, not an "offline" screen, so that I can
  fix the real problem.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Server reachable (normal start) | Unchanged: boot screen, then the app with the restored queue. The check costs one ping round trip. |
| Signed out on the phone | Unchanged: the login page. No check is waited for. |
| Server answers but refuses the credentials | Treated as reachable: the normal start runs and brings the login page back. |
| No network at all (aeroplane mode) | Boot screen shows "Geen netwerkverbinding" with the three buttons. |
| Network, but no server (server down, proxy answers 502/503/504, captive portal, timeout after 3 s) | Boot screen shows "Server niet bereikbaar" with the three buttons. |
| "Opnieuw proberen" | One more check. Reachable: the normal start continues. Otherwise the panel stays, updated to the new answer. |
| "Wachten op server" | A calm waiting state: title "Wachten op de server", "Wachten sinds 14:03", "Volgende poging over 5 s". Attempts after 2, 5, 10, 20 s and then every 30 s, and at once when Android reports a network. No queue restore and no error messages meanwhile. When the server answers, the normal start continues by itself, full queue included. "Opnieuw proberen" and "Offline verder" stay available. |
| "Offline verder" | The app starts with the downloaded library. The queue keeps only the tracks that are on the device; the track that was playing stays current if it is downloaded, else the next downloaded one. A strip above every page says "Offline: alleen muziek op dit toestel" and, when tracks were left out, "12 nummers niet beschikbaar offline", with an "Opnieuw verbinden" button. |
| Offline, and the server comes back | Detected in the background (same backoff, and at once on a network change). Offline mode ends, the strip disappears, a toast says "Weer verbonden", and the full queue comes back — unless the listener started other music while offline, which is then left alone. |
| Offline, in the car | Android Auto shows the downloaded library instead of timing out on each list. |

## Acceptance Criteria

1. With the server reachable, a start looks and behaves exactly as before; the check adds no visible delay.
2. With aeroplane mode on and a signed-in phone, the boot screen says there is no network and offers
   "Opnieuw proberen", "Wachten op server" and "Offline verder".
3. With the server stopped but Wi-Fi on, the boot screen says the server is not reachable, with the same
   three buttons.
4. "Offline verder" opens the app with only downloaded music; the queue holds only downloaded tracks and the
   strip names how many were left out.
5. "Wachten op server" shows since when it waits and when the next attempt is; starting the server makes the
   app continue by itself with the full queue.
6. In offline mode, starting the server makes the strip disappear and puts the full queue back if the listener
   had not replaced it.
7. A refused password never leads to the offline screen; it leads to the login page.
8. With Android Auto connected in offline mode, the car shows downloaded music, not errors or endless loading.

## Open Questions / Not Yet Decided

- Ratings made while offline are not queued: the rating call fails as it does today on a dropped connection.
  Scrobbles already queue durably natively (bug report 071) and are delivered when the server is back.
  Queuing ratings is left as a follow-up issue.
- Android Auto connecting while the app is *not* in offline mode (cold start in the car with the server down,
  or during "Wachten op server") still uses the online service and its timeouts. Deferred; see the technical
  design.
