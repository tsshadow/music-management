- **Vijf daily mixes in plaats van één.** `rules_genres` kreeg een `hardness`-kolom (0-100,
  bewerkbaar op de genre-edit-pagina naast de hiërarchie): geseed met een handmatige lijst
  ankers (Deep House 10 tot Speedcore 100) en overgeërfd via `rules_subgenre_hierarchy` voor
  elk genre zonder eigen anker. Een track leent, als hij zelf geen gescoord genre draagt, de
  hardheid van zijn label, dan van zijn artiest, dan van zijn tempo. `GET /api/feeds` somt nu
  zes tegels op met titel en subtitel: `daily-mix-soft`/`-mid`/`-hard` verdelen de eigen
  luistergeschiedenis in drie tertielen (Zachter, Middenin, Harder), `daily-mix-artist` en
  `daily-mix-label` draaien dagelijks door de top 10 artiesten/labels — welke van de tien het
  wordt, bepaalt een hash van gebruikersnaam en datum, niet een toevalsgenerator. `daily-mix`
  blijft werken als alias van `daily-mix-mid`, zodat auto en telefoon niets hoeven te wijzigen.
