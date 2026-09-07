- **De helft van de pipeline draaide op de container die naast GitLab zelf staat.** De CI-LXC deelt
  node `server` met gitlab (cap 15G) en lms (cap 11,9G, en die zit eraan); de caps van alle CT's
  samen zijn 58G op 30G fysiek geheugen. Alle jobs die hun omgeving in een Docker-image meedragen
  (`mobile:format`, `mobile:lint`, `mobile:unit`, `mobile:build-debug`, `muma:smoke`, `muma:images`,
  `muma:e2e`) dragen nu de `fast`-tag, zodat het werkstation ze overneemt zodra het aan staat.
- **Jobs die hun toolchain van de host lenen blijven bewust ongetagd.** De twee runners draaien niet
  dezelfde versies (LXC: Python 3.11, node 24; werkstation: Python 3.13, node 20), dus
  `backend:unit`, `frontend:*` en `frontend:e2e` zouden een andere uitslag geven afhankelijk van
  welke runner het eerst polt. Een nieuwe policy-test houdt daarnaast de jobs met productie-
  credentials — deploy, tag, APK-upload — permanent op de LXC. `backend:integration` en
  `muma:contracts` horen ook in die groep: die starten hun database wél in Docker maar draaien
  `python3 -m pytest` vanaf de host, en faalden op het werkstation in vijf seconden met `No module
  named pytest`.

<!-- release notes -->

- **Pipelines belasten de server minder.** Zware bouw- en testjobs verhuizen naar het werkstation
  zodra dat aan staat, in plaats van naast GitLab te draaien.
