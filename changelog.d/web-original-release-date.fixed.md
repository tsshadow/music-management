- **De web-UI toonde het jaar waar de app de hele datum liet zien.** LMS stuurt twee datums: `date`
  is de datum van deze editie, `originalDate` de oorspronkelijke release. MuMa schrijft de datum die
  hij uit de NFO haalt in ORIGINALDATE, dus juist die tweede is de interessante -- een scene-tag als
  `2026-00-00` komt aan als een kaal jaar, terwijl `originalDate` `2026-09-03` bevat. De web-UI las
  alleen `date` en toonde dus "2026", terwijl "Recent uitgebracht" wél op de originele datum
  sorteerde: dezelfde track beweerde twee dingen op één scherm. De keuze volgt nu dezelfde regel als
  de Android-app al gebruikte -- neem de originele datum alleen als hij minstens zo precies is -- en
  staat in één gedeelde `trackDate.js` in plaats van twee kopieën van dezelfde datumfunctie.

<!-- release notes -->

- **Nummers tonen weer hun echte releasedatum in de web-speler en de tracklijst**, in plaats van
  alleen het jaar. De app deed dit al goed.
