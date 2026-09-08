- **Zestien afleveringen van één radioshow stonden als zestien versies van één nummer.** De
  groepering kijkt naar artiest en titel, en een set of aflevering draagt elke week dezelfde titel:
  16 keer "Andromedha Guest Mix" van een uur, 14 keer "The Boom Room", 11 keer "Forerunners Guest
  Mix". Gemeten op productie: 214 works met in totaal 560 lange opnames, waarvan er **346 zouden
  verdwijnen** zodra het canonical-filter uit fase 2 aangaat — een jaar wekelijkse show
  teruggebracht tot één aflevering. Een opname langer dan 15 minuten krijgt nu een eigen work en
  groepeert niet meer op titel.
- De grens is niet gevoelig gekozen: van de tracks in works met meer dan één versie lopen er 576
  langer dan 10 minuten en 566 langer dan 20. Alles wat lang is in deze bibliotheek is dus héél
  lang, en elke waarde in die lege band scheidt dezelfde twee populaties. Een lange track groepeert
  daarmee ook niet meer met een korte versie van dezelfde naam; dat kost een extended mix zijn plek
  naast de radio-edit, en dat is de veilige kant: iets twee keer tonen is beter dan het verbergen.
- **Elke SoundCloud-rip telde als officiële release.** De worker vroeg of een bestand in het
  downloadarchief stond door de bestandsnaam te vergelijken met `downloads_soundcloud_archive.filename`
  — maar alle 157.393 rijen daarin bevatten een absoluut pad, dus die vergelijking kon nooit waar
  zijn. Gevolg: de 1.162 SoundCloud-tracks die óók een label dragen kregen de provenance-bonus die
  voor een officiële release bedoeld is, en konden dus de release verslaan waar ze een rip van zijn.
  Precies de omkering die deze scoring moest wegnemen. Beide archieven worden nu op het volledige
  pad gematcht (SoundCloud in `filename`, YouTube in `path`), geïndexeerd door `migrate_v23`.
- `scripts/repair_song_works.py` verplaatst de al gegroepeerde afleveringen zelf: het herberekent
  elke sleutel en meldt deze apart als `long-form`. Voor de scores is er een nieuwe vlag,
  `--rescore-downloads`, die de gelabelde downloads uit hun work haalt zodat de worker ze met de
  gerepareerde test opnieuw beoordeelt. Beide zijn dry-run-baar; draai eerst `--dry-run`.

<!-- release notes -->

- Afleveringen van een radioshow met dezelfde naam worden niet langer als versies van één nummer
  behandeld.
- Een SoundCloud-rip kan de officiële release waar hij vandaan komt niet meer verslaan.
