- **Elke tagger-ronde zette dezelfde 768 verdwenen bestanden opnieuw in de wachtrij.** De
  scanner houdt rijen voor bestanden die hij sindsdien niet meer zag (`__TODO`-releases die
  de importer heeft verplaatst); de anti-join van 0.67.0 zette die elke ronde in de wachtrij,
  de wachtrij-pass zag dat ze niet op schijf staan en gooide de rij weg, en de volgende ronde
  begon opnieuw. Een verdwenen bestand houdt nu zijn rij als grafsteen (reden `missing`,
  geen mtime): komt het terug, dan tagt de eerstvolgende walk het alsnog.

<!-- release notes -->

- **De tagger draaide elke ronde rondjes om 768 verdwenen bestanden.** Gestopt.
