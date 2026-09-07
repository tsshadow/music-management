- **De nachtelijke image-refresh liet twee productie-images achter op de base waar ze op gebouwd
  zijn.** Die taak herbouwt `muma-base` met `--no-cache` en pusht hem, dus die pakt de
  Debian-security-pakketten van die dag mee — maar `muma-telegram` en `muma-importer` bleven staan
  op wat hún laatste build erfde, en dat is de release. Zo dook `CVE-2026-33164` (libde265, HIGH,
  upstream al gefixt) op in beide images terwijl de base waar ze op gebouwd zijn al schoon was. Er
  was geen pin om te bumpen: de images waren simpelweg ouder dan hun base. De refresh herbouwt nu de
  hele familie die FROM `muma-base` komt; een test leidt die lijst af uit de Dockerfiles, dus een
  nieuwe worker-image kan hem niet stilletjes missen.
- Ontwikkelketen: `postcss-selector-parser` naar 7.1.6 (GHSA-w9m9-85wc-3x92, denial of service via
  ongecontroleerde AST-recursie). Dev-dependency van de eslint-keten, komt niet in een image terecht.

<!-- release notes -->

- Beveiligingsupdates voor de telegram- en importer-containers landen nu elke nacht in plaats van
  pas bij de volgende release.
