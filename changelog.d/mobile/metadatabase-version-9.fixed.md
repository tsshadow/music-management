- **De app opende zijn eigen cache niet meer en noemde dat een verbindingsfout.** 6.32.0 gaf de
  track-entity `workId`, `isCanonical` en `versionKind` maar liet `MetaDatabase` op versie 8 staan,
  dus Room vond een database met een andere vorm dan de code verwacht en weigerde hem te openen:
  "Room cannot verify the data integrity". Elk scherm dat de metadata-cache aanraakt -- bibliotheek,
  genres, zoeken, downloads -- liep daarop stuk; in één diagnoserapport 304 keer. De cache wissen
  hielp tot de volgende database aan de beurt was, want er staat er één per server plus de offline
  database. De database staat nu op versie 9, met een migratie die de drie kolommen alleen toevoegt
  als ze ontbreken -- versie 8 bestaat in twee vormen in het veld en een `ALTER TABLE` op een kolom
  die er al is breekt de migratie af.

<!-- release notes -->

- **De bibliotheek, genres en zoeken gaven een verbindingsfout die geen verbindingsfout was.** De
  app kon zijn eigen cache niet meer openen na de vorige update. Dat is hersteld; de cache wissen is
  niet meer nodig.
