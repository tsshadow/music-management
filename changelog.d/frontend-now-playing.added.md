- **Een tik op de minispeler op de telefoon opende voorheen niets.** Die tik opent nu een full-screen
  "Nu speelt"-scherm (cover, titel/artiest, sterren, seekbar, shuffle/vorige/afspelen/volgende/herhalen,
  een equalizer- en een wachtrijknop), te sluiten via de chevron, een swipe omlaag op de cover of de
  terugknop. De wachtrij opent op de telefoon voortaan als bottom sheet in plaats van nergens. De deep
  link die de melding op Android gebruikt (`player`) opent dit scherm op de telefoon; op desktop blijft
  hij het wachtrijpaneel openen. Shuffle en herhalen sturen op de telefoon (native afspelen) nog
  dezelfde browser-only stores aan als altijd — dat op de afspeeldienst zelf laten werken is een
  bekende openstaande vervolgstap, niet in deze wijziging opgelost.

<!-- release notes -->

- Een tik op de minispeler opent op de telefoon nu een "Nu speelt"-scherm met cover, sterren, seekbar
  en alle afspeelknoppen, met een eigen wachtrij-bottom-sheet.
