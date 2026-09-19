- **De ster, shuffle, herhaal en nieuws waren uit het rijscherm van Android Auto verdwenen;
  alleen vorige/volgende bleven over.** Niet door de Capacitor-overstap: een bugreport van de
  telefoon laat zien dat de app alle vier de acties nog publiceert (de notificatie toont ze ook) en
  dat Android Auto, op 12 september bijgewerkt naar 17.6, ze laat vallen. Het nieuwe mediascherm
  tekent alleen acties waarvan de extras een `CommandButton.ICON_*`-constante noemen; onze knoppen
  droegen alleen een eigen drawable. Elke autoknop noemt nu zo'n constante naast zijn drawable:
  shuffle, herhaal (uit/één/alles) en nieuws hun eigen, de ster `STAR_UNFILLED` bij geen
  beoordeling, `STAR_FILLED` bij één tot vier en `HEART_FILLED` bij vijf -- media3 kent geen
  cijfersterren, dus in de auto zie je een tik van één naar vier niet verspringen. De notificatie
  houdt de genummerde sterren.

<!-- release notes -->

- **De ster, shuffle, herhaal en nieuws staan weer op het rijscherm van Android Auto.** Android
  Auto 17.6 tekent alleen knoppen met een standaard-icoon; de app geeft die nu mee. In de auto is de
  ster leeg, gevuld of een hart (vijf sterren); het cijfer blijft op de telefoon.
