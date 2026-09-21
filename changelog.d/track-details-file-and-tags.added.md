- **Nummerdetails tonen nu het bestand en alle tags.** De sheet achter `⋮` (en nu ook achter een
  tik op de titel in de speler) verborg bestandsnaam en formaat achter een inklapbare "Technische
  details" die alleen bitrate en pad liet zien. Er staat nu een vaste sectie *Bestand* met
  bestandsnaam, `MP3 · 320 kbps · 44,1 kHz · stereo · 9,8 MB`, map en de dag van toevoegen -- alles
  wat LMS al meestuurde en de UI weggooide -- plus een sectie *Tags* die MuMa bij het openen vraagt
  via het nieuwe `GET /api/library/tracks/by-path`: kanaal met platform, bron-URL, herkomst, BPM,
  catalogusnummer, copyright, originele artiest/titel, remixer, en daaronder elke overige tag uit
  het ingestion-record. Een bestand dat MuMa niet kent geeft geen tags-sectie; een MuMa die niet
  bereikbaar is zegt dat, zodat het niet leest als "dit bestand heeft geen tags".

<!-- release notes -->

- **Nummerdetails tonen nu het bestand en alle tags.** Tik op de titel in de speler (of `⋮`) voor
  bestandsnaam, formaat, map, kanaal, bron-URL, BPM, catalogusnummer en alle overige tags.
