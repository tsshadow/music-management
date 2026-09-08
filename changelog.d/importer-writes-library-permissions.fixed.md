- **Elke geïmporteerde release landde onschrijfbaar voor iedereen behalve root.** De importer draait
  als root met de standaard umask, dus wat hij uitpakt en verplaatst komt binnen als `root:root`,
  mappen `0755` en bestanden `0644`. Root merkt daar niets van — het verplaatsen, het taggen en de
  scan slagen allemaal — maar over SMB krijgt de share-gebruiker `other::r--` en faalt elke latere
  schrijfactie met `[Errno 13] Permission denied`.
- Gemeten op 2026-09-08 over de EPs-mappen die sinds 2026-09-01 zijn aangeraakt: **631 op `0777`,
  19 op `0755`** — precies de mappen die zijn aangemaakt nadat de handmatige rechtenreparatie van
  2026-09-05 langs de boom was gegaan. De release-date backfill liep op 9 bestanden daaruit vast.
  Een sweep repareert wat er op dat moment staat en zegt niets over de import van morgen, en dat is
  de reden dat dit in de importer thuishoort en niet in een script.
- `make_library_writable()` zet na de verplaatsing mappen op `0777` en bestanden op `0666` — wat de
  rest van de bibliotheek draagt sinds de reparatie van 5 september. Het draait vóór de tagronde,
  want die is de eerste die naar deze bestanden schrijft; als root zou die het toch wel redden, maar
  alles daarna niet.
- Best effort, en het zegt het als het misgaat: een `chmod` die niet plakt levert een WARNING per
  pad en een telling op, geen mislukte import. De release staat op dat moment al op zijn plek, en
  hem dan alsnog laten falen zou de bibliotheek in een slechtere staat achterlaten dan een bestand
  dat alleen leesbaar is.

<!-- release notes -->

- Nieuwe imports komen binnen met dezelfde rechten als de rest van de bibliotheek, zodat het taggen
  en de backfills er daarna nog bij kunnen.
