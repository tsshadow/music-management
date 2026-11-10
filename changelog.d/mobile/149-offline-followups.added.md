- **A rating given while the server is out of reach is kept and sent later.** In offline mode, or
  when a request gets no answer from the server, the rating waits in a queue on the phone, the same
  way listens do, and goes out as soon as the server answers again, also after a restart. The last
  rating per track wins: rate a track 3 and then 5 offline, and the server gets only the 5. Before
  this, the stars jumped back and the rating was lost (#149).
- **Android Auto shows the downloaded music when the server is down, also without "Offline
  verder".** A car that connects with the home server off (a cold start in the car, or a phone on
  "Wachten op server") checks the server once, at most 3 s, and then browses the downloaded library
  instead of timing out on each list. While it browses it asks again every 20 s and goes back to the
  server when it answers (#149).

<!-- release notes -->

- Een beoordeling zonder verbinding met de server blijft bewaard en gaat naar de server zodra die
  terug is.
- Android Auto toont de gedownloade muziek als de server uit staat, ook zonder "Offline verder".
