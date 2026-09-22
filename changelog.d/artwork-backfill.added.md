- **Een backfill die de hoes inbedt in bestanden die er zonder binnenkwamen.**
  `scripts/backfill_artwork.py` vult aan wat de downloaders hadden moeten meeschrijven:
  387 van 149.626 SoundCloud-nummers hadden een hoes, en 4.132 van 53.702 YouTube-nummers.
  Opnieuw per bestand via yt-dlp zou 200.000 extracties zijn tegen een host die een burst met
  403 beantwoordt; dat hoeft niet. SoundCloud beantwoordt `tracks?ids=<50>` met een
  `artwork_url` per track en de id's staan al in het archief, dus de hele bibliotheek is
  ~3.000 verzoeken. Een YouTube-thumbnail is adresseerbaar vanaf het video-id, dus die kant
  vraagt geen enkele API. Alleen bestanden zonder afbeelding worden aangeraakt, een track
  waarvoor het platform geen hoes heeft blijft leeg (níét de avatar van de uploader), en een
  URL die geen http(s) is wordt geweigerd — `urllib` spreekt ook `file://`, en die URL komt
  uit andermans JSON. Draai hem met `--dry-run`, dan `--account <kanaal>`, dan de rest.

<!-- release notes -->

- **Bestaande downloads kunnen hun hoes alsnog krijgen** met `scripts/backfill_artwork.py`.
