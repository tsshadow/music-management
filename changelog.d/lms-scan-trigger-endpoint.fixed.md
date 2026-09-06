- **muma heeft LMS nooit verteld dat er iets veranderd was.** Er waren twee antwoorden op de
  vraag "waar staat LMS": de radioplanner las `LMS_URL` / `LMS_HOSTS` / `MUMA_SERVER_HOSTS` uit
  de omgeving en werkte, `LmsScanTrigger` las de instelling `lms_hosts` uit de configuratie —
  en `docker-compose.yml` vult die nergens, de regel staat uitgecommentarieerd. Wie nooit met de
  hand een host op de beheerpagina heeft ingevuld, had dus een scan-trigger die niets deed. Stil,
  want het verzendpad keerde zonder één logregel terug: een bibliotheek die een verplaatste map
  pas uren later oppikte, las als een probleem van LMS. Hetzelfde gold voor de API-sleutel, die
  onder twee namen door compose komt en waarvan de trigger er maar één kende. Beide antwoorden
  komen nu uit één plek, `services/common/Helpers/LmsEndpoint.py`: de instelling wint, de
  omgeving is de terugval, en als geen van beide iets oplevert zegt het log één keer precies wat
  er ontbreekt in plaats van niets.

<!-- release notes -->

- **Wijzigingen kwamen niet in de muziekserver terecht tot de volgende volledige scan.** muma
  wist niet waar hij hem moest bereiken, en zei dat niet.
