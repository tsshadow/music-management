- **Een afgekeurde "artiest" als `001` zette bijna de hele bibliotheek in de retag-wachtrij.**
  Een regelwijziging vertaalt naar bestanden via een brede match: artiestnaam, titel *of pad*
  bevat de term. Voor een catalogusnummer of jaartal is dat elk pad. Het afkeuren van ~480
  cijfer-artiesten op 17 september markeerde 149.213 bestanden, waarvan er 6.168 die naam
  daadwerkelijk als artiest droegen; de tagger liep een dag door bestanden waar niets aan te
  veranderen viel en de genrebeslissingen die erachter stonden kwamen niet aan bod. Een
  afkeuring markeert nu alleen de bestanden die de naam vandaag als artiest hebben, en een
  term zonder één letter doet nergens meer een substring-match. Het herstelscript voor de
  bestaande wachtrij staat in `scripts/prod/clear-spurious-artist-retag-marks.sh`.

<!-- release notes -->

- **Een afgekeurde "artiest" als `001` zette bijna de hele bibliotheek in de retag-wachtrij.**
  Een afkeuring raakt nu alleen de nummers die die naam echt als artiest hebben, in plaats van
  elk bestand met dat cijfer ergens in het pad.
