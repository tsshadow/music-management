- **Een rating vanaf de telefoon kwam als 500 terug zolang muma zijn uursync draaide.** De
  song-versie-sync liep 285.000 tracks langs met per rij een `UPDATE ... WHERE` die alleen bij een
  verschil iets schreef — maar een UPDATE die niets raakt neemt het schrijfslot van SQLite tóch, van
  de eerste rij van een chunk tot de commit. De artiestafbeeldingen deden hetzelfde in één transactie
  van 11.762 rijen. LMS wacht daar niet op: een Dbo-transactie leest eerst en schrijft dan, en een
  lezer die wil schrijven terwijl het slot bezet is krijgt van SQLite direct `SQLITE_BUSY`, zonder
  dat de busy-timeout meedoet. Dus `insert into "rated_track" ... database is locked`, een 500 in de
  app, en de rating weg. Tien minuten per uur, elf keer in de logs op één ochtend.
- Beide syncs lezen nu eerst en schrijven alleen het verschil, in korte transacties: de
  versie-kolommen in batches van honderd, de afbeeldingen per artiest. Na de eerste ronde klopt bijna
  alles al, dus wordt er bijna niets geschreven en is het slot bijna nooit bezet.
<!-- release notes -->
- Een rating of scrobble vanaf de telefoon mislukte tien minuten per uur, zolang muma op de
  achtergrond zijn versie-model naar de server schreef. Die sync houdt het slot van de server nu
  niet meer vast.
