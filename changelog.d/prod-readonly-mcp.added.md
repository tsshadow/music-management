- **Een agent kon productie alleen lezen door er als root op te SSH'en.** "Read-only" was een
  instructie in een skill-tekst, dus precies zo betrouwbaar als het model dat hem las, en elke
  databasevraag ging via het applicatie-account dat óók mag schrijven. Er is nu een MCP-server
  (`tools/muma_mcp`, draait lokaal, praat naar prod via de bestaande `/health`- en
  `/api/system/*`-endpoints plus een eigen databaseaccount) met zes tools: `prod_health`,
  `prod_containers`, `prod_logs`, `prod_tables`, `prod_describe` en `prod_query`. De grens ligt in
  de database: `muma-readonly` heeft `SELECT, SHOW VIEW` op één database, geen `FILE` — dus ook
  geen `SELECT ... INTO OUTFILE` — en `MAX_QUERIES_PER_HOUR 2000` plus `MAX_USER_CONNECTIONS 3`
  zodat een agent in een lus door MariaDB zelf wordt afgekapt. Daarbovenop weigert een guard alles
  wat niet met `SELECT`/`WITH`/`SHOW`/`DESCRIBE`/`EXPLAIN` begint, strípt hij commentaar vóór hij
  het sleutelwoord leest (`/*!…*/` wordt door MariaDB uitgevoerd, dus een validator die naar de
  originele tekst kijkt leest eroverheen) en gaat elke query in `START TRANSACTION READ ONLY` met
  `max_statement_time=10`. Logoutput gaat langs een maskeerfilter, want containerlogs bevatten
  echt credentials. `scripts/prod/create-readonly-db-user.sh` maakt het account aan;
  `scripts/prod/install-muma-mcp.sh` registreert de server en beweert niet dat hij read-only is
  maar probeert een `CREATE TABLE` en faalt als die slaagt.

<!-- release notes -->

- **Claude kan productie nu veilig uitlezen** — logs, containerstatus en de database — via een
  account dat op databaseniveau alleen mag lezen, in plaats van via een root-shell.
