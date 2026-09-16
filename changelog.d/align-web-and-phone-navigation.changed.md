- **Web-sidebar en telefoon-Bladeren zijn nu één lijst.** `Sidebar.svelte` en `BrowseGrid.svelte`
  hadden elk een eigen kopie van de bibliotheeksecties, met eigen volgorde en deels andere iconen;
  beide lezen nu `navigation.js`, en een test houdt de gerenderde sidebar en het gerenderde grid aan
  dezelfde set. Wat er anders wordt: de telefoon krijgt "Nummers" (of "Sets", naar de actieve modus)
  als eerste tegel — de volledige lijst was daar alleen via de Home-tegels bereikbaar — en de tegels
  staan in de volgorde van de sidebar. "Luisteren" heet in beide "Luisterstatistieken", zodat de
  luisterpagina herkenbaar is als de statistieken die het zijn. Op de telefoon blijft "Bladeren" ook
  actief op de pagina van één genre, label, jaar of lineup en op de nummers/sets-lijst, zoals dat al
  voor een artiest of album gold.

<!-- release notes -->

- Web en telefoon bieden dezelfde bibliotheekingangen in dezelfde volgorde; de telefoon heeft er
  "Nummers"/"Sets" bij en "Luisteren" heet nu "Luisterstatistieken".
