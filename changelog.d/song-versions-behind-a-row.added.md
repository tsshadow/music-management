- **Achter elke regel zit nu de lijst met versies van dat nummer.** De knop staat naast de
  songtekst-knop en verschijnt alleen bij een nummer dat de server heeft gegroepeerd. De lijst
  toont per versie het type (radio, extended, original), het formaat en de bitrate, met de
  canonical gemarkeerd als beste versie — en elke versie speelt direct af.
- De lijst wordt opgehaald en niet afgeleid uit wat op het scherm staat. De regel die je ziet ís de
  versie die de server koos; de andere zijn samengeklapt voordat de browser ze zag.
  `getSpotifyTracks?workId=<id>` levert ze mét afspeelbare id's, wat muma's eigen versie-API niet
  kan: die kent paden en muma-id's, en daar heeft de speler niets aan.
- Een nummer waarvan er maar één versie is zegt dat, in plaats van een lege lijst te tonen.
