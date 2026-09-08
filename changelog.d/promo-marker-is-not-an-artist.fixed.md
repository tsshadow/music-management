- **9.188 tracks stonden op naam van een artiest die niet bestaat.** SoundCloud zet een marker vóór
  de echte credit — `PREMIERE ｜ TARS - Rumble [NNVA03]`, `FREE DOWNLOAD - Exilles - Crude
  Definition`. De artiestenregels knippen de titel in segmenten en kiezen het segment dat het beste
  matcht met een naam in `library_artists`. Zodra een marker die wedstrijd één keer wint, staat hij
  *in* `library_artists`, matcht daarna perfect met zichzelf en wint elke volgende titel: 9.188
  tracks onder "Premiere", 329 onder "FREE DOWNLOAD", 43 onder "PREVIEW". Bij 3.874 daarvan staat de
  echte artiest nog gewoon in de titel, waar de regel hem heeft laten liggen.
- De ignore-lijst kende deze namen niet, en zou ze ook niet hebben tegengehouden: beide regels die
  hem lezen (`CheckArtistRule`, `AddMissingArtistToDatabaseRule`) kijken pas naar de ignore-lijst
  *nadat* ze `library_artists` hebben geraadpleegd, en al deze namen staan in `library_artists`.
  `InferArtistFromTitleRule` trekt de ignore-lijst zonder correctie nu af van de namen waartegen hij
  mag matchen, dus een marker kan niet meer uit een titel gekozen worden en het segment met de echte
  artiest komt aan de beurt. Een naam mét correctie blijft wél kiesbaar — dat is precies hoe
  `CheckArtistRule` de kans krijgt de juiste spelling erin te zetten.
- `migrate_v22_promo_marker_artists.sql` zet elf markers op de ignore-lijst. Er wordt niets
  verwijderd: de artiestenrijen blijven staan en hun tracks houden wat ze hebben tot de deep run het
  bestand opnieuw leest. Een artiestenrij weggooien zou `library_tracks.primary_artist_id` en
  `library_works.primary_artist_id` verweesd achterlaten, waar geen foreign key op staat.
- **De brede pijp `｜` werd op drie plekken niet herkend.** SoundCloud gebruikt hem omdat `|` niet in
  een bestandsnaam mag, dus de twee betekenen hetzelfde — maar `InferArtistFromTitleSingleDashRule`
  en de laatste-redmiddelregel vervingen alleen de ASCII-versie. `PREMIERE ｜ TARS - Rumble` viel
  daardoor uiteen in twee segmenten waarvan het eerste `PREMIERE ｜ TARS` was: een artiestennaam die
  nooit heeft bestaan. Eén `normalise_pipes()` voor alle regels.

<!-- release notes -->

- **"Premiere" is geen artiest.** Een SoundCloud-titel begint vaak met een marker als PREMIERE of
  FREE DOWNLOAD, en die belandde als artiestennaam op de track — 9.188 keer, terwijl de echte
  artiest in de titel bleef staan. Elf van die markers staan nu op de negeerlijst en worden niet
  meer als artiest gekozen; bestaande bestanden worden bijgewerkt zodra de tagger ze opnieuw leest.
