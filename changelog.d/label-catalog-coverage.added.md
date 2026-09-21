- **Hoe compleet de catalogus van een label is, staat nu op de labelpagina.** Dirty Workz nummert
  zijn releases `DWX0001` tot `DWX2212`; wie 001–303 en 305–309 heeft, moest tot nu toe een
  mapoverzicht sorteren om te zien dat 304 er niet is. Beheer > Labels > label krijgt een sectie
  Catalogus die de nummers uit de mapnamen van de releases leest (er is nergens een kolom voor;
  `LabelPath.split` van de tagger levert de releasemap, ook bij een geneste map) en ze per reeks
  groepeert: `DWX`, `DWXCD`, `DWXCVR`. Per reeks het waargenomen bereik, hoeveel daarvan aanwezig
  is, een balkje, en de niet-aanwezige nummers als reeksen (`DWX0177, DWX0287–DWX0289`), met een
  knop die ze voluit, één per regel, naar het klembord kopieert -- dat is waar je mee zoekt. Een
  variant (`DWX1105D`, `DWX0544-`) vult zijn positie en wordt apart genoemd; wat geen nummer heeft
  (`DWXFREE`) staat onder Overig en telt nooit als gat. Het nummer is de laatste cijferreeks, drie
  cijfers of meer tenzij een streepje hem van de prefix scheidt, zodat `247HC001`, `AFT3R001`,
  `R909-29` en `DWXCD-050` goed vallen. De pagina zegt bewust "niet aanwezig" en nooit
  "ontbreekt": vóór het laagste en na het hoogste nummer wordt niets geclaimd, en een label kan
  nummers overslaan. Eén verkeerd getypte map die een reeks tot boven de 20.000 nummers oprekt,
  geeft alleen nog een telling. `GET /api/curation/labels/{naam}/catalog`, op aanvraag berekend
  uit één query; geen kolom in het labeloverzicht, geen afschrijftabel -- dat zijn latere stappen
  (docs/designs/label-catalog-coverage).

<!-- release notes -->

- **Hoe compleet de catalogus van een label is, staat nu op de labelpagina.** Per reeks (`DWX`,
  `DWXCD`, ...) het waargenomen bereik, hoeveel daarvan aanwezig is, en de niet-aanwezige nummers
  als reeksen, met een knop die ze als zoektermen kopieert. "Niet aanwezig", niet "ontbreekt":
  een label kan nummers overslaan.
