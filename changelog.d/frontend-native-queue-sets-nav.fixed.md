- **"Toevoegen aan wachtrij" bereikte de afspeeldienst op de telefoon nooit.** De webinterface
  beslist wat er in de wachtrij staat maar houdt hem niet vast, dus elke wijziging reist als één
  `setQueue` met de héle lijst. Stond het spelende nummer niet in die lijst — en dat is de gewone
  toestand na een kaartje op het startscherm of een zoekresultaat — dan werd de lijst weggegooid en
  ging alleen dat ene nummer over. Het toegevoegde nummer zat niet in het bericht en werd dus nooit
  gespeeld; vóór 0.60.2 begon de spelende set er ook nog van vooraf aan. Een nummer zonder lijst
  erachter gaat nu vóór de wachtrij in plaats van ernaast, precies zoals de browser met dezelfde
  stores doet, en toevoegen, hierna afspelen, verwijderen, herordenen, leegmaken en "speel deze
  lijst vanaf hier" sturen allemaal de complete wachtrij met de juiste positie mee. De UI volgt
  daarnaast een `next` van de notificatie nu ook als het bericht over de nieuwe status nog niet was
  aangekomen — twee losse berichten over de brug lieten de app een nummer achterlopen.

- **De knop "Sets" onderin de app navigeerde niet.** Een tik zette de weergave op `sets` terwijl de
  modus nog op `songs` stond, en het effect dat die twee gelijk houdt zette de weergave meteen weer
  terug: het adres bleef `/songs` en de merkkleur bleef groen. Beide helften verhuizen nu samen, en
  de schakelaar in de zijbalk op een groot scherm blijft werken zoals hij werkte.

<!-- release notes -->

- **"Toevoegen aan wachtrij" deed niets in de nieuwe interface op de telefoon.** Het toegevoegde
  nummer gaat nu echt de wachtrij in, zonder dat het spelende nummer opnieuw begint.

- **De knop "Sets" onderin de app navigeerde niet.** Nu wel.
