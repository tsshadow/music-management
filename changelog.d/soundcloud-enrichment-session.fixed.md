- **Een promo- of follower-only track kwam binnen zonder genre, tags en omschrijving, en zonder
  regel in het archief.** De download zelf loopt door `YoutubeDL` mét de ingelogde
  Firefox-cookies en de bijpassende user agent -- daar is deze downloader voor -- maar de
  verrijking erna (`SoundcloudSongProcessor._fetch_enriched_info`) startte een kale
  `yt-dlp --dump-single-json` zonder cookies en zonder user agent. SoundCloud beantwoordt zo'n
  anonieme aanvraag voor een niet-openbare track met 401, en juist alleen voor die tracks,
  waardoor het jarenlang op een incidentele storing bij SoundCloud leek. Op 23 september ging het
  vier keer mis op 53 downloads: `thesplitter/dreaming` en drie promo's van `merciless_music`,
  elk 0,8 seconde na de eigen regel "Postprocessing downloaded file" -- de gecredentialiseerde
  aanvraag voor exact dezelfde track was dus net gelukt. De verrijking stuurt nu dezelfde sessie
  mee als de download. Wat verloren ging was de rij in `downloads_soundcloud_archive` en de
  tags uit `--dump-single-json`; het bestand zelf stond er gewoon.

<!-- release notes -->

- **Promo- en follower-only tracks van SoundCloud kwamen binnen zonder genre, tags en
  omschrijving.** De stap die die gegevens ophaalt was niet ingelogd en gebruikt nu dezelfde
  sessie als de download.
