- **De Python-tooling in CI installeert niet meer bij elke job opnieuw.** `backend:format`,
  `backend:lint` en `backend:typecheck` draaien in een `python:3.14-slim`-container en deden elk
  een verse `pip install -r requirements-dev.txt` naar een weggooi-`/tmp`; drie keer dezelfde
  wheels per pipeline, en op 2026-09-18 — PyPI leverde een uur lang 80–260 KB/s — liep elk van de
  drie tegen de 10-minutengrens van de job, op beide runners, twee pipelines achter elkaar. De
  installatie landt nu in `~/.cache/muma-python-tooling/<sleutel>` op de runner (sleutel = hash van
  `requirements-dev.txt` plus het image), als bind mount in de container; alleen de eerste job na
  een requirements-bump praat nog met PyPI, de rest vindt de tools klaarstaan. Drie jobs die
  tegelijk starten delen de map onder een `flock`; een afgebroken installatie laat geen
  `.complete`-marker achter en wordt gewoon opnieuw gedaan. Sleutels die een maand niet zijn
  aangeraakt worden opgeruimd. `PYTHON_TOOLING_CACHE=none` zet het uit. Gemeten: eerste run 14 s
  voor drie gelijktijdige jobs, warme run 1 s.
