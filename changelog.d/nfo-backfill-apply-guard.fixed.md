- **De NFO-backfill controleerde zijn eigen voorwaarde niet meer op het moment dat hij schreef.**
  `plan_release` weigert een bestand dat al een `ORIGINAL_ARTIST` heeft en weigert een regel die
  andere artiesten noemt dan het bestand bevat — maar dat oordeel staat in een plan dat uren oud is
  tegen de tijd dat het geschreven wordt. De volledige planfase over 48.958 releasemappen duurde
  zes uur, en de tagger schrijft ondertussen naar diezelfde bestanden: sinds 0.51.0 legt
  `CaptureDisplayArtistRule` bij elke download een credit vast. `apply_plan` stelt de vraag nu per
  bestand opnieuw en slaat over wat inmiddels een eigen credit heeft (`skipped_gained_original`) of
  wat de wording niet meer beschrijft (`skipped_artists_changed`), in plaats van een verse waarde
  te overschrijven met een verlopen.
- Het `.failed`-bestand bevatte alleen paden, terwijl `--from-plan` `wording<TAB>pad` leest. Het
  bestand dat je overhield om geweigerde schrijfacties later opnieuw te draaien, was dus precies
  het formaat dat niet teruggelezen kon worden — de wording stond nergens anders. Het wordt nu in
  het planformaat weggeschreven.

<!-- release notes -->

- De backfill die artiestennamen uit NFO-bestanden herstelt, controleert vlak voor het schrijven
  opnieuw of het bestand nog steeds die naam mist, in plaats van te vertrouwen op een plan van uren
  eerder.
