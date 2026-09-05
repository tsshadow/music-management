- **Het script dat het read-only databaseaccount aanmaakt kon niet draaien, en gaf soms stilletjes een
  leeg wachtwoord.** Twee onafhankelijke fouten, allebei zichtbaar geworden toen musicserver op
  2026-09-05 herstartte. Het root-wachtwoord werd gelezen uit `/tmp/.env.music-management`, en `/tmp`
  overleeft een reboot niet — de database was de hele tijd op en gezond, maar het bestand was weg. Er
  wordt nu eerst in de draaiende container gekeken (`docker inspect`), wat net zo goed "wat de stack
  echt gebruikt" is en wél een herstart doorstaat; het bestand blijft de terugval. En de
  wachtwoordgeneratie gebruikte `tr -dc ... | head -c 32`, wat onder `set -o pipefail` een val is:
  `head` sluit de pipe na 32 bytes, `tr` krijgt SIGPIPE en de pipeline eindigt op 141 — maar alleen
  soms, afhankelijk van of `tr` nog een keer schrijft voordat hij het merkt. De eerste run haalde het
  net wel, daarna niet meer, en het script stopte zonder één regel uitvoer. De invoer wordt nu vooraf
  begrensd en met `cut` afgeknipt, en een wachtwoord dat geen 32 tekens is laat het script hard falen.
