- **Wat yt-dlp over een download wist wordt nu bewaard.** De postprocessor kreeg de volledige
  info-dict, de tagger pikte er vier velden uit (`BaseSong._apply_extra_info`) en de rest verdween
  zodra het proces verderging. SoundClouds `genre`, `tags` en `description`, YouTubes
  `artists`/`track`/`album`/`release_year` uit het muziek-credits-paneel, en de hoofdstukindeling
  van een set van twee uur stonden nergens opgeschreven — over 53.295 YouTube- en 157.387
  SoundCloud-rijen. Nieuwe kolom `info_json` op `downloads_soundcloud_archive` en
  `downloads_youtube_archive` (`migrate_v21_download_info_json.sql`).
- De blob wordt eerst gesnoeid (`services/downloader/info_json.py`). `formats`, `thumbnails` en
  `automatic_captions` zijn transportdetails die binnen een paar uur verlopen en vormen bijna het
  hele gewicht van de 100-800 KB die een ruwe YouTube-dict weegt; wat overblijft is 5-15 KB, met een
  harde bovengrens. Een `description` die daar in z'n eentje overheen gaat wordt weggelaten; blijft
  het dan nog te groot, dan slaat de rij niets op in plaats van een halve JSON.
- Vooruit-werkend, met opzet. Bestaande rijen blijven `NULL`: voor SoundCloud terughalen zou één
  `yt-dlp --dump-single-json` per track kosten en die kant beantwoordt een burst met 403. Op de
  YouTube-kant vult een herdownload wél een lege kolom aan, want die tabel is echt op
  (video_id, download_type) gesleuteld.
- Er wordt niets mee gedaan bij het taggen. Dit legt alleen vast wat de downloader te horen kreeg.

<!-- release notes -->

- **Downloads bewaren nu wat SoundCloud en YouTube erover vertelden.** Genre, tags, omschrijving en
  de artiestcredits gingen tot nu toe verloren zodra het bestand binnen was.
