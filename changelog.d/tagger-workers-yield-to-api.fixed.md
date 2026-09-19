- De tagger legde de API plat zodra een grote retag-wachtrij leegliep. Hij draait in hetzelfde
  proces als music-manager en gaf 16 threads een pagina van 500 bestanden zonder adempauze; na de
  0.67.0-deploy stonden 32.000 Youtube-bestanden in de wachtrij en gaven `/health` en
  `/api/auth/login` ruim een uur geen antwoord, terwijl LMS in milliseconden reageerde -- inloggen
  op de webpagina leek daardoor "stuk". De pool krijgt nu 12 threads (`TAGGER_WORKERS`) en werkt
  per plak van twee bestanden per thread, met daarna een pauze van 0,5 s (`TAGGER_BATCH_PAUSE`)
  waarin alleen de event loop het proces heeft. Een plak waarin niets geparsed hoefde te worden
  kost geen pauze, dus een ongewijzigde dagwandeling wordt er niet langzamer van.
