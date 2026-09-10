- **De releasedatum-sync had de bibliotheek elk uur leeggehaald.** Productie draait twee servers:
  `stable`, waar iedereen van speelt, en `alpha`, waarvan de database zes weken oud is en 330.153
  tracks bevat tegen 338.662, met 194.816 datums tegen 238.207. De sync draaide per server, net als
  de sync die gebruikers, playlists en song-versies naar elke server schrijft — dus wie het laatst
  draaide besliste, en alpha zou zo'n 43.000 datums wissen en de 8.500 tracks die hij nooit gezien
  heeft leegmaken. Een feit dat je *uit* de servers leest moet je over alle servers samen beslissen
  voordat je iets wegschrijft; dat is de omgekeerde richting van de syncs ernaast en vraagt de
  omgekeerde opzet. "Deze server kent dit bestand niet" en "dit nummer heeft geen datum" zijn nu
  twee verschillende antwoorden.
- **`library_tracks.release_date` kent drie toestanden en het verschil tussen twee ervan telt.**
  NULL betekent dat geen enkele server het bestand heeft — een gat, en de feed valt dan nog terug op
  de kolom van de ml-analyzer. De lege string betekent dat een server het bestand wél heeft en er
  geen datum is waar iedereen het over eens is; dat is een besluit, en de feed respecteert het in
  plaats van terug te vallen op precies de waarde die zojuist tegengesproken werd. Daarom leest
  `feeds/queries.py` nu een CASE en geen COALESCE.
- **Een jaartal naast een dagdatum is precisie, geen tegenspraak.** Een FLAC met `2026` en een MP3
  met `2026-09-04` zijn één release op twee precisies; `2019` naast `2026-09-04` is dat niet en
  levert geen datum op. De sync gooide het jaartal eerder weg vóórdat hij op tegenspraak controleerde.
- **De feeds in de auto deden niets na een herstart van de dienst.** Een tik komt binnen op de
  session-callback-thread, en daar werd de netwerkcall rechtstreeks gedaan: op de main thread levert
  dat `NetworkOnMainThreadException` op, wat de app opving als "lege feed" — een knop die stilletjes
  niets doet. Loopt nu via de service-scope, net als de sterren- en random-paden ernaast.
- De tweede feed-cache naast de repository is weg. Die kende dag noch server, dus na middernacht
  speelde "alles afspelen" de ranglijst van gisteren, en na het wisselen van account of server die
  van de vorige gebruiker — met de track-ids van de vorige server. De cache die overblijft is op
  slug, dag én server gesleuteld, en onthoudt een half opgeloste feed niet meer voor de rest van de
  dag.
