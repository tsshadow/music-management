- **Een hertag van een download was blind voor alles wat de downloader wist.** yt-dlp overhandigt
  zijn info-dict één keer, aan de postprocessor; elke keer daarna loopt de tagger over de
  bestandsboom en roept `parse_folder(channel, song_type)` aan zonder `extra_info`. Wat de eerste
  ronde niet in de tag schreef, was daarna onbereikbaar. Sinds 0.51.0 bewaart de archiefrij een
  gesnoeide kopie van die dict, en die werd door niets gelezen — de kolom lag er, de hertag ging er
  langs.
- `services/tagger/download_info.py` leest hem terug en `Tagger.parse_song` geeft hem door aan
  dezelfde `BaseSong._apply_extra_info` die de downloadkant gebruikt. Die vult een tag alleen als
  hij leeg is; het genre is de uitzondering en gaat daarna langs `ResolveGenreRule`, precies zoals
  elk ander afgeleid genre — een geblokkeerd genre komt er dus niet via deze weg alsnog in.
- Gematcht op het absolute pad dat het archief opschreef, en op niets anders. De tagger loopt over
  de schijf en leert nooit een video-id, dus het pad is de enige sleutel die beide kanten hebben.
  Een bestand dat sinds zijn download is verplaatst of hernoemd vindt niets en wordt getagd zoals
  het vandaag is. Bewust geen terugval op de bestandsnaam: twee kanalen met hetzelfde bestand
  zouden dan stilletjes elkaars metadata krijgen.
- `migrate_v23_download_archive_path_index.sql` indexeert de kolom waarin elk van de twee tabellen
  dat pad houdt — SoundCloud in `filename`, YouTube in `path`. Zonder index is dit een volledige
  scan over 157.393 respectievelijk 53.366 rijen per bestand.
- Vooruit-werkend, net als de kolom zelf: 77 rijen dragen vandaag een info-dict, elke nieuwe
  download komt erbij. Er wordt niets teruggehaald bij SoundCloud, want die kant beantwoordt een
  burst met 403.

<!-- release notes -->

- Wat de downloader over een nummer te horen kreeg, wordt nu ook gebruikt als MuMa datzelfde
  bestand later opnieuw tagt.
