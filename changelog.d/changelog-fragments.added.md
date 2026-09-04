- **De changelog wordt niet meer op een feature branch bewerkt.** Elke wijziging legt een eigen
  bestandje neer in `changelog.d/`, en de release voegt ze samen onder de nieuwe versiekop. Dat is
  geen cosmetiek: het gedeelde `[Unreleased]`-blok merget niet alleen luidruchtig (een conflict
  tussen twee branches van dezelfde dag), maar vooral stil. Ships er een release terwijl jouw
  branch openstaat, dan ziet git "wij voegden regels toe" en "zij voegden een versiekop van twee
  regels in", past allebei toe, en jouw regels staan onder een versie die zonder ze naar productie
  ging. Vier branches in één sessie, en niets ving het: geen test leest de changelog, en
  `release-version-check.sh` controleert alleen dát er een gedateerde regel voor `VERSION` staat,
  niet wat erin staat. Een fragment is een nieuw bestand met een naam die niemand anders gebruikt,
  dus er valt niets te mergen. `muma:changelog` faalt een MR die er geen meebrengt, tenzij het
  label `no-changelog` erop zit.

<!-- release notes -->

- **Wijzigingen worden voortaan per stuk vastgelegd en pas bij een release samengevoegd.** Dat
  voorkomt dat een regel onder de verkeerde versie belandt, wat eerder gebeurde zonder dat iets
  het merkte.
