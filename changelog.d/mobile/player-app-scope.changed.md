- **De speler hoort nu bij de app in plaats van bij het hoofdscherm.** `MediaPlayerManager` en
  `MediaPlayerLifecycleSupport` stonden in `scope<NavigationActivity>` en waren daarmee onzichtbaar
  voor alles wat Koin via de root scope oplost: een gewone `Fragment`, een `BroadcastReceiver`, een
  root `single`. Omdat `by inject()` lui is, viel dat pas om bij het eerste gebruik — vaak binnen een
  `catch`, zodat het eruitzag alsof er niets gebeurde. Het kostte twee releases, waaronder
  bugrapport 031 (de app verdween bij het starten zodra de auto verbonden was). Ze zijn nu gewone
  `single`s: één speler, overal bereikbaar, en die hele soort fout bestaat niet meer.
- Starten en stoppen mag nu vaker dan één keer. De speler overleeft het draaien van het scherm en
  het afsluiten via het menu, dus `onCreate()` en `onDestroy()` zijn een herbruikbaar paar geworden:
  de tweede start herstelt de bewaarde wachtrij niet bovenop de lopende en registreert geen tweede
  koptelefoon-ontvanger, en na een afsluiting werkt dezelfde instantie weer volledig. Tegelijk is dit
  het voorwerk voor de universele UI, waarin de native laag zonder `NavigationActivity` moet draaien.

<!-- release notes -->

- De speler zit niet langer vast aan het hoofdscherm. Dat haalt de crash weg die de app liet
  verdwijnen zodra je in de auto stapte, en laat de muziek ongestoord doorlopen als een scherm
  opnieuw wordt opgebouwd.
