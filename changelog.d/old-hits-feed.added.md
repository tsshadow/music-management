- **New feed "Oude hitjes": old favourites you play less.** The daily mixes lean on recent
  releases, so an old anthem rated five stars never came back without a search -- on production
  702 old tracks carry 4-5 stars and 584 old tracks played three or more times had not been played
  in six months. The new feed (100 tracks, stable for a day, "Meer laden" like the others) fills
  about 40% with your own old 4-5 star songs, 30% with old songs you played at least three times
  but not in six months, and 30% with known hits by artists you rate or play: an artist's top
  tracks on Deezer (and Last.fm when `lastfm_api_key` is set), or songs the library holds four or
  more versions of. "Old" is released more than three years ago by the earliest date of any version;
  anything rated 1-2 or played in the last 90 days is left out, one version per song, at most three
  per artist. It shows after the daily mixes on Home and the phone's "Daily mixes" page, at
  `/old-hits`, and via `GET /api/feeds/old-hits`. A new hourly `popular-tracks` loop fetches the
  top lists for the ~940 artists that matter (a 4-5 star track or five listens), weekly per artist,
  at most four requests a second, sending only artist names, into the new tables
  `artist_popular_tracks` and `artist_popularity_fetches` (migrate_v49). Every threshold is a
  setting in the "Feeds" group (`old_hits_*`, `popular_tracks_*`).

<!-- release notes -->

- **New feed "Oude hitjes".** Old favourites you have not heard in a while, old songs you used to
  play a lot, and the well-known old hits of artists you like -- on Home after the daily mixes.
  Popularity comes from Deezer's top tracks per artist (only artist names are sent); Last.fm is
  used too once an API key is set.
