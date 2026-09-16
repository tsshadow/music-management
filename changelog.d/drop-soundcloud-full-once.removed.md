- **`muma-soundcloud-worker-full-once` is uit de stack.** De eenmalige volledige SoundCloud-sweep
  (`--no-break-on-existing`, zonder `--repeat`) stond sinds 0.27.0 voor niets: de downloader doet
  zelf elke `deep_sweep_days` een deep pass, en juist het uitzetten van break-on-existing was wat
  de 429's opleverde. De container stond als "offline" op het Beheer-overzicht en als vaste
  uitzondering in de nachtelijke check; beide zijn weg. `--remove-orphans` bij de volgende deploy
  ruimt hem op prod op.
