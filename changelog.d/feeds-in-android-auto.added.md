- De release radar en de dagelijkse mix zijn nu te starten vanuit de auto. MuMa rangschikt de feed
  en kent zijn tracks alleen bij bestandspad; de server kent ze bij id. Het nieuwe
  Subsonic-endpoint `getSongsByPath` legt die brug — het lost bibliotheekrelatieve paden op naar
  afspeelbare songs, in de volgorde waarin ze gevraagd zijn, en laat een pad dat de server niet
  heeft weg in plaats van de hele aanvraag te laten mislukken.
- `library_tracks.release_date`, elk uur overgenomen uit de server (`ORIGINALDATE`, anders `DATE`)
  door dezelfde lms.db-pas die gebruikers, playlists en song-versies al synchroniseert. Beide feeds
  filteren op een releasedatum en lazen die tot nu toe uit `library_track_audio_features`, een
  kolom die de ml-analyzer vult: op productie stond die nul keer gevuld en dekte hij een kwart van
  de bibliotheek, dus zowel de radar als de dagelijkse mix gaf altijd nul tracks terug. Twee
  bestanden onder één track die het oneens zijn leveren geen datum op, en een datum die verdwijnt
  wordt teruggeschreven als NULL — anders blijft een track na een tagcorrectie voor altijd in de
  radar staan.
