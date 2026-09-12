- **"Ik zie eigenlijk alleen zwart wit": het beginscherm van de Kotlin-app had geen enkele
  merkkleur en de speler stond vol met Material-lila.** Gemeten op een API 34-emulator: van de
  2.527.200 beeldpunten op het beginscherm waren er nul groen, en het enige kleurvlak was een
  `#4a4458` paars dat in geen van beide stijlen voorkomt. Drie oorzaken, alle drie een kleur die
  niemand gekozen heeft. Beide stijlen overschrijven Material3's primaire en oppervlakteattributen
  maar lieten de secundaire reeks onaangeroerd, dus alles wat die aansprak kreeg het lila van de
  bibliotheek — en de navigatiebalk tekent de vorm achter het actieve tabblad juist met
  `colorSecondaryContainer`. De hoesvervanger sprak diezelfde reeks aan, dus een nummer zonder hoes
  werd een `#ccc2dc` vlak: op de speler 822.514 beeldpunten, bijna een derde van het scherm. En de
  notenglyph van een nummer zonder hoes was hard op `#000000` getint, wat 1,12:1 haalt op een
  venster dat in beide stijlen bijna zwart is — die stond er dus wel en was onzichtbaar. De
  secundaire reeks is nu in beide stijlen benoemd, de hoesvervanger tekent op
  `colorSurfaceVariant` met `colorInkTertiary` (3,92:1 in de MuMa-stijl, 7,03:1 in Spotify, boven
  de 3:1-ondergrens voor wat getekend en niet gelezen wordt), de notenglyph neemt
  `colorControlNormal` (8,8:1) en de vorm achter het actieve tabblad neemt de merkkleur van de
  modus op een vijfde — groen voor nummers, blauw voor sets, dezelfde sterkte waarmee een
  geselecteerde regel al getint wordt. Voor de volledigheid: de sets-schakelaar in de werkbalk
  werd groen op het ene moment dat de app juist blauw is, en leest nu ook de modus.
