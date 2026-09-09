- **De lms.db-sync gaf het op als de server nog aan het migreren was.** Bij een deploy herstarten
  beide diensten tegelijk en muma wint meestal: hij synchroniseert vóórdat de server zijn eigen
  schemamigratie heeft toegepast, ziet geen versiekolommen en slaat over. Overslaan is juist —
  schrijven in een schema dat halverwege een migratie staat is precies wat je niet doet — maar er
  kwam daarna niets meer terug, dus de kolommen bleven leeg tot iemand de container met de hand
  herstartte.
- Dat gebeurde bij de deploy van 0.54.0: de sync sloeg over om 20:16, en zonder die handmatige
  herstart had die release een functie uitgebracht die stilletjes niets deed.
- De sync probeert het nu opnieuw zolang een database om die ene reden is overgeslagen: zes pogingen,
  een minuut ertussen, en daarna een waarschuwing met hoeveel servers nog niet klaar zijn. Alles
  anders — een vergrendelde database, een onbereikbare server, helemaal geen lms.db — is al
  best-effort binnen de sync zelf en krijgt hier bewust geen tweede ronde.
- De logregel zegt nu ook wélke server hij overslaat. Er draaien er twee, een stabiele en een alpha,
  en een regel zonder naam kost je de tijd om dat uit te zoeken.
