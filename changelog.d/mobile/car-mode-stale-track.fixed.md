- **Het rijscherm bleef het eerste nummer van de rit tonen.** Met shuffle aan publiceerde
  `MediaPlayerManager` de positie in de afspeelvolgorde, terwijl de Capacitor-plugin de
  tijdlijn-index verwachtte die hij zelf aan `seekTo` had gevraagd; die twee kwamen nooit
  overeen, de verwachting bleef staan en elke latere wissel werd onderdrukt. Zonder shuffle
  onzichtbaar. De plugin krijgt nu altijd de tijdlijn-index, geeft een verwachting na drie
  gelijke meldingen op, en het webdeel volgt ook een `durationchange` op track-id
  (`docs/bug-reports/032`).

<!-- release notes -->

- **Het rijscherm loopt weer mee** met het nummer dat speelt, ook met shuffle aan.
