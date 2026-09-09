- **LMS weet nu welke bestanden hetzelfde nummer zijn.** muma bepaalde dat al — het heeft de
  label-provenance en de downloadarchieven die beslissen welke versie wint, en LMS heeft geen van
  beide — maar het bleef in muma's eigen database staan. De server krijgt vier kolommen op `track`
  (`work_id`, `is_canonical`, `version_kind`, `version_score`, migratie naar databaseversie 118) en
  muma vult ze in dezelfde lms.db-ronde die al gebruikers, playlists en artiestafbeeldingen
  synchroniseert. Geen endpoint, geen API-sleutel, geen HTTP in het bladerpad.
- Het Subsonic-antwoord voor een nummer draagt `workId`, `isCanonical` en `versionKind` mee. Er wordt
  **niets gefilterd**: de web-UI heeft juist alle versies nodig om ze tot één regel te bundelen en de
  rating en genres van die bundel op te tellen. Additieve velden; bestaande clients merken niets.
- **De brug is het bestandspad**, want een LMS-track-id en een muma-track-id hebben niets met elkaar
  te maken. `library_paths.candidate_paths()` kent elke schrijfwijze die het proberen waard is en
  wordt hier hergebruikt in plaats van een tweede matcher — twee kopieën van die regel die uit elkaar
  lopen is precies hoe gespiegelde ratings ooit op een dood id belandden.
- **Alles wat onbekend is blijft zichtbaar.** Een track die muma nog niet heeft gegroepeerd — op elk
  moment ongeveer de helft van de bibliotheek, terwijl de worker zijn achterstand wegwerkt — houdt
  `is_canonical` op 1 en krijgt een lege `work_id`. Hetzelfde voor een pad dat niet matcht. Een
  filter hierop moet falen richting een bestand twee keer tonen, nooit richting muziek verbergen die
  bestaat.
- Een rij die eerder een antwoord kreeg wordt actief gecorrigeerd in plaats van met rust gelaten:
  zonder dat blijft een track die na een split zijn werk verliet voorgoed verborgen.
- De sync slaat een server die de migratie nog niet heeft gedraaid over in plaats van te falen — dat
  gat bestaat tussen het uitrollen van de images en de eerste start van de server — en een vergrendelde
  database kost deze ronde en niets meer.
