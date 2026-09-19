- Elke deploy zette de hele Youtube-boom (32.000 bestanden) opnieuw in de retag-wachtrij.
  `scripts/deploy.sh` draait elke `migrate_*.sql` bij elke deploy, en stap 3 van
  `migrate_v7_youtube_category_genres.sql` markeerde onvoorwaardelijk `%/Youtube/%` voor een
  rescan -- zonder reden, dus in de wachtrij zichtbaar als "(walk)". Sinds het wachtrijmodel van
  0.67.0 werkt de tagger dat direct na de start op volle snelheid af, en dat is wat op 2026-09-19
  de API ruim een uur onbereikbaar maakte. De markering gebeurt nu alleen op de run die
  daadwerkelijk een categorie-rij toevoegde of besliste; op elke volgende deploy raakt de migratie
  geen bestand meer aan.
