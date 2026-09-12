- **Afspelen zit vanaf nu achter een platformlaag, en er verandert niets zichtbaars.** `Player.svelte`
  deed alles zelf met zijn `<audio>`-element — laden, spelen, spoelen, volume, de equalizer, de
  Media Session, en een eigen timer omdat de browser van de tv geen `timeupdate` stuurt — en dat is
  precies het stuk dat op een telefoon door `PlaybackService` gedaan wordt. Die motor staat nu in
  `src/lib/platform/`, achter één `platform`-object met `player`, `storage`, `speech`, `diagnostics`
  en `system`; de implementatie wordt één keer gekozen bij het importeren, en dat ene punt is waar
  een Capacitor-schil zich later inhaakt. Wachtrij, shuffle, radio, nieuws en jam-sync bleven staan
  waar ze stonden. Dezelfde DOM, dezelfde knoppen, dezelfde 1.318 bestaande tests ongewijzigd groen.
  Fase 0 van `docs/designs/universal-ui/`.

<!-- release notes -->

- De webspeler is van binnen opgeruimd: het afspelen zelf staat nu los van het scherm eromheen,
  zodat de telefoon-app er later dezelfde code voor kan gebruiken. Aan wat je ziet of hoort
  verandert niets.
