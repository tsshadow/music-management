- **Van interface wisselen zette je op het beginscherm van de telefoon in plaats van in de nieuwe
  app.** De nieuwe interface kwam op, stond er ongeveer een seconde, en verdween. De schakelaar
  zette namelijk ook de launcher om, en Android gooit élke taak weg waarvan de starter net is
  uitgezet — dat was precies de taak waarin de gebruiker stond, met de zojuist gestarte interface
  erin. De vier launcher-ingangen wijzen nu allemaal naar een onzichtbaar tussenactiviteitje dat de
  instelling leest en doorstuurt, zodat er nooit meer iets wordt uitgezet waar de gebruiker in zit.
  Beide richtingen blijven op de emulator staan, ook 15 seconden later, en het icoon opent na een
  force-stop de gekozen interface. Hetzelfde gold ongemerkt voor het wisselen van de icoonkleur
  vanuit de app; ook dat kan nu geen taak meer opruimen. Een snelkoppeling op het beginscherm volgt
  vanaf nu de instelling in plaats van de interface van de dag dat hij gemaakt werd.
- **Elke wijziging in de wachtrij begon het nummer waar je naar luisterde opnieuw.** De webspeler
  bezit de wachtrij maar kan hem niet vasthouden, dus "voeg toe aan wachtrij" komt binnen als de
  hele lijst opnieuw; de app wiste de lijst en sprong naar het begin. Een set die 176 seconden liep
  stond daarna op 5. De app vergelijkt nu eerst: staat op de gevraagde plek het nummer dat al
  speelt, dan wordt alleen de lijst eromheen herbouwd en wordt de speler niet aangeraakt — gemeten
  op de emulator liep de stand door 75 → 142 → 149 seconden over drie wachtrijwijzigingen heen. Is
  het een ander nummer, dan begint dat gewoon vooraan. Kan de speler het niet, dan wordt de
  wachtrij alsnog vervangen, maar terug naar de stand van daarvoor in plaats van naar nul — een gat
  van een fractie van een seconde in plaats van drie minuten.
- **Op een server zonder https bleef in de nieuwe interface elke hoes leeg.** De pagina zelf liep
  onder `https://localhost`, en een plaatje van een `http://`-server is dan gemengde inhoud die de
  WebView weigert. De gedocumenteerde instelling daarvoor (`allowMixedContent`) bleek niets te doen:
  de app las hem, de WebView stond op "altijd toestaan", en Chromium blokkeerde de plaatjes toch.
  De pagina draait nu zelf op `http://localhost`, waarmee het verschil verdwijnt. Een https-server
  werkt onveranderd.

<!-- release notes -->

- **Wisselen tussen de klassieke en de nieuwe interface werkt.** Voorheen kwam je een seconde later
  op je beginscherm terecht in plaats van in de app.
- **De wachtrij aanvullen begint je nummer niet meer opnieuw.** Een set van drie minuten sprong
  eerder terug naar het begin.
- **Hoesjes zijn ook zichtbaar op een server zonder https.**
