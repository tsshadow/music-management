- **De dagelijkse mix en de release radar staan nu ook in de web-UI en op de telefoon**, niet alleen
  in de auto. Op het startscherm staan ze bovenaan als twee rijen; "toon alles" opent de hele feed
  met een afspeelknop, op `/daily-mix` en `/release-radar`.
- **De rij die "Release Radar" heette op het webstartscherm was de radar niet.** Dat was
  `getSpotifyPlaylist?id=spotify:release_radar`: de hele bibliotheek onder tien minuten, gesorteerd
  op releasedatum — dezelfde lijst voor elke luisteraar, persoonlijk in naam alleen. MuMa's echte
  radar weet wat dit account draait en neemt de naam en de plek over. Het server-endpoint blijft
  bestaan voor wie het nog aanroept.
- Een feed die leeg terugkomt laat zijn rij weg in plaats van een kop boven niets te zetten. Leeg is
  een echt antwoord — er kwam deze week niets uit dat past — en dat hoort er anders uit te zien dan
  een lijst die nog laadt.
