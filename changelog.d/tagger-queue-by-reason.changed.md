- **De tagger is een wachtrij-consument; de mapwalk is een dagelijks vangnet.** Elke
  vijf-minutenronde deed tot nu toe de wachtrij én daarna een walk over alle 327k
  bestanden, en die walk begon na elke deploy opnieuw bij EPs. De ronde doet nu alleen de
  wachtrij; de walk draait als de vorige ouder is dan `tagger_walk_interval_hours`
  (standaard 24, `0` is het oude gedrag), en het moment van de laatste walk staat op schijf
  zodat een deploy hem niet opnieuw start. `NU RETAGGEN` en `OPNIEUW VAN VOREN` doen alleen
  de wachtrij; `FORCEER VOLLEDIGE RESCAN` en `POST /api/tagger/tag/all` ook de mappen.
- **De wachtrij bedient beslissingen vóór bulk.** Genre- en artiestbeslissingen, regels en
  handmatige retags gaan eerst, dan bestanden die de scanner kent maar de tagger nooit zag,
  dan `rescan_all` en `deep_run`, dan rijen zonder reden. De deep run, de knop "rescan all",
  rerun-parse en de handmatige file-retag schrijven nu allemaal hun reden mee. Index
  `(needs_rescan, rescan_reason, filepath)` (`migrate_v30`) vervangt die van v28.
- **Een bestand dat iemand met de hand neerzet wordt gevonden zonder walk.** Elke ronde
  zet de anti-join `library_media_files` minus `tagger_processed_files` in de wachtrij
  (reden `new_in_library`), beperkt tot de mappen en extensies die de walk zelf doet.
  Bijvangst: de 1.402 EPs-bestanden met `.MP3` in hoofdletters, die de hoofdlettergevoelige
  glob van de walk nooit zag, worden zo alsnog getagd.

<!-- release notes -->

- **De tagger werkt alleen nog de wachtrij af en loopt de mappen één keer per dag.** Een
  beslissing in Curatie gaat nu vóór een "rescan all" van een maand geleden, en een bestand
  dat je met de hand neerzet wordt gevonden zodra de scanner het kent.
