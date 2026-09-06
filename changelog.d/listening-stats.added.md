- **MuMa heeft sinds maart 2024 luisterbeurten opgeslagen en ze nooit teruggegeven.** `/history`
  somde ze één voor één op, niemand telde ze. Er is nu een pagina **Luisteren** met totalen, een
  tijdlijn, een uur-van-de-dag- en dag-van-de-week-grafiek, je meest gedraaide tracks, artiesten en
  labels, en waar je luisterde — over 30 dagen, 12 maanden of alles. Zeven nieuwe leesendpoints
  onder `/api/listening`; geen nieuwe tabellen.
- **De pagina zegt zelf wat ze niet weet, boven de grafieken in plaats van eronder.** 33.461 van de
  53.760 opgeslagen luisterbeurten (62%) zijn nooit aan een track in de bibliotheek gekoppeld: die
  tellen mee in de totalen, de tijdlijn en de bronnen, maar kunnen in geen ranglijst voorkomen. En
  maar 876 luisterbeurten hebben ooit vastgelegd hóe lang er gespeeld is, dus de luistertijd is een
  schatting die uitgaat van uitgespeelde tracks — `measured_secs`, `imputed_secs` en
  `estimated_secs` zijn drie aparte velden, geen samengevoegd getal dat een aanname als meting
  presenteert.
- **Uren en dagen staan in jouw tijdzone, niet in die van de database.** De databasecontainer draait
  op UTC, dus `HOUR()` zou een luisterbeurt van half één 's nachts in Amsterdam op de vorige dag om
  half elf zetten. De client stuurt een IANA-zonenaam mee en de indeling gebeurt in Python; een
  vaste offset zou de ene helft van het jaar goed zetten en de andere kapot maken.
- **Een API-sleutel van een gebruiker leest alleen de eigen geschiedenis.** `?username=` van een
  ander levert 403. De LMS-proxy geeft querystring en sleutel ongewijzigd door en controleert zelf
  niets, dus zonder deze check kon één sleutel ieders luistergeschiedenis lezen.
- Nieuwe index op `listened_at` in beide scrobble-tabellen (`migrate_v20_listening_indexes.sql`): de
  bestaande unique keys beginnen op `username` en helpen niet voor een vraag zonder gebruikersnaam.

<!-- release notes -->
- **Nieuwe pagina "Luisteren".** Wat je gedraaid hebt, wanneer en hoe vaak — totalen, een tijdlijn,
  je luisteruren per dag en per weekdag, en je meest gedraaide tracks, artiesten en labels, over 30
  dagen, 12 maanden of je hele geschiedenis.
- De pagina is eerlijk over wat MuMa niet weet: 62% van de opgeslagen luisterbeurten is nooit aan
  een track gekoppeld en telt daarom wel in de totalen mee maar niet in de ranglijsten, en de
  luistertijd is een schatting. Allebei staan ze boven de grafieken in plaats van in een voetnoot.
