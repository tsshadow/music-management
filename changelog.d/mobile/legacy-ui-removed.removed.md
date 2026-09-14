- **De klassieke Kotlin-interface is uit de app.** Sinds 6.36.0 stonden er twee interfaces in de
  APK: de oude schermen (fragments, lay-outs, navigatiegraaf, instellingenscherm, wizard,
  handleiding) en de webshell met de Svelte-speler. De webshell is nu de enige. Het
  launcher-icoon, een melding, de widget, de snelle-instellingen-tegel en een snelkoppeling openen
  allemaal dezelfde `CapacitorActivity`; "Terug naar de klassieke interface" en de instelling
  `webUiEnabled` zijn weg, net als "Alle app-instellingen…". De zoek-intent van de Assistent
  ("speel X af in MuMa") komt nu via de trampoline binnen en gaat dezelfde route.
- Wat blijft is alles wat de schermen niet waren: de afspeeldienst, downloads en de Room-cache,
  Android Auto, automodus, stem, de crashrapporten, de widget en de plug-ins die de webshell
  aanspreekt. De favoriete tegels die Auto onder "Afspeellijsten" toont worden nog uit de oude
  tegelopslag gelezen — er is alleen niets meer dat ze schrijft, dus wat op het toestel staat
  blijft staan en nieuwe komen er niet bij.
- 141 Kotlin-bronbestanden en 63 testbestanden, 95 lay-outs, 13 menu's en bijna 7.000 regels
  strings, kleuren en stijlen weg; de Navigation-, ViewPager-, RecyclerView-, Markwon- en
  ConstraintLayout-afhankelijkheden mee. Dit is een opruiming, geen nieuwe functie — het
  versienummer van de app maakt de sprong naar 7.0.0 omdat een upgrade een interface kwijtraakt
  die iemand nog aan kon hebben staan.

<!-- release notes -->

- **De klassieke interface is weg.** De app opent altijd in de nieuwe speler; de knop "Terug naar
  de klassieke interface" en het oude instellingenscherm bestaan niet meer. Afspelen, downloads,
  Android Auto, automodus en stem werken zoals voorheen.
