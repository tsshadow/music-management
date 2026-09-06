- **De originele artiestschrijfwijze bleek niet vanzelf terug te komen, en is nu terug te halen uit
  de NFO.** Sinds 0.47 bewaart `CleanTagsRule` "Eternate & Prosphere" in `TXXX:ORIGINAL_ARTIST`
  vlak voor hij het in twee waarden splitst. De aanname daarbij was dat bestaande bestanden dat
  vanzelf zouden oppikken bij hun volgende tagronde. Dat klopt niet: een bestand dat al gesplitst
  is heeft niets meer te splitsen, dus de capture vuurt nooit meer. Gemeten over 400 bestanden
  onder de EPs-root draagt 120 een gesplitste artiest en **geen enkele** nog de originele
  schrijfwijze — voor de bestaande bibliotheek was het veld dus permanent leeg, niet tijdelijk.
  De NFO die met de release meekomt is geschreven vóór dat splitsen en zegt het nog wel.
  `scripts/backfill_original_artist_from_nfo.py` leest die tracklist, koppelt op tracknummer aan
  het bestand ernaast, en schrijft de schrijfwijze terug. De klep die dat veilig maakt: een regel
  wordt alleen gebruikt als die, gesplitst met de eigen regel van de tagger, exact dezelfde
  artiesten oplevert als er al in de tag staan — een write kan dus alleen de schrijfwijze
  herstellen en nooit een artiest toevoegen, weglaten of hernoemen. Dry run standaard.
  Alleen de EPs-boom heeft NFO's; Soundcloud, Youtube en artists hebben er nul, dus die vallen
  hier buiten.

<!-- release notes -->

- **"Henk feat Kees" is terug te halen voor releases die al in de bibliotheek stonden.** Een nieuw
  script leest de originele schrijfwijze uit het NFO-bestand dat met de release meekwam.
