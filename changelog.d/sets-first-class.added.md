- **Sets kregen geen eigen afspeelknoppen.** De speler (desktop-balk en Now Playing) toont voortaan
  −30 s/+30 s-knoppen naast play/pause zodra het geladen nummer een set is (dezelfde tien-minuten-
  grens als de rest van de app, `isSet` uit `downloads.js`), rekent positie en duur in h:mm:ss in
  plaats van m:ss, en vervangt de klikbare balk door een `<input type="range" step="1">` zodat een
  positie in een bestand van twee uur ook echt te verslepen is; de pijltjestoetsen op die balk
  springen ±30 s in plaats van de standaard 1 s-stap. Songs-modus verandert niet. `TrackList`'s
  duurkolom toont voor een set nu h:mm in plaats van m:ss, per rij bepaald (niet per modus), zodat
  een gemengde lijst nooit de verkeerde vorm toont.
- **Setpositie volgde het apparaat niet.** Een nieuwe `setResume`-sleutel in de account-
  instellingenblob (dezelfde blob als favoriete genres en taal) onthoudt de laatst gespeelde positie
  per werk-id, met een cap van 50 en een throttle van 15 s tijdens het afspelen plus een directe
  schrijving bij pauzeren, wisselen van nummer en `beforeunload`. Bij het starten van een set met een
  bewaarde positie tussen de eerste en de laatste minuut springt de speler er automatisch naartoe en
  toont een meldingsknop "Opnieuw" om alsnog van voren te beginnen. Werkt zowel via de browser-
  engine als via de native speeldienst (`platform.player.state()`).

<!-- release notes -->

- Sets krijgen ±30 s-knoppen, een h:mm:ss-tijdweergave en een sleepbare seekbalk in de speler, en
  onthouden voortaan waar je gebleven was — op elk apparaat.
