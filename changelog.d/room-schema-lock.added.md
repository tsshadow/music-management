- **Een Room-schema dat van vorm verandert zonder van versienummer te veranderen laat CI nu vallen.**
  `services/muma-mobile/app/schemas/identity-hashes.json` legt de identity hash van elk geëxporteerd
  schema vast, en `tests/ci/test_room_schema_versions.py` vergelijkt. Zo'n wijziging was tot nu toe
  een schone diff in een gegenereerd bestand, en de app merkte het pas op de telefoon van iemand die
  zijn cache al gevuld had.
