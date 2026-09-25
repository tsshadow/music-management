- **Every track now has a form -- track, set, live set or podcast -- and a live set files under
  the year it was played.** Until now "what is this file" was only guessed from its folder or its
  length, so no filter could ask for live sets and leave the weekly radio shows out, and a Defqon.1
  2012 recording uploaded in 2016 filed under 2016. `library_tracks` gets `form` and
  `performance_date` (`migrate_v42_track_form.sql`, columns only), LMS gets the same two columns
  (migration step 122, database version 123). The form is derived from length (under ten minutes
  is always a track -- the short files under `Podcasts/` and `Top 100/` are countdown tracks), top
  folder (`Livesets`, `Telegram`, `Podcasts`) and the festival and podcast rules the tagger already
  uses (`services/common/track_form.py`); a live set whose festival and year have an edition date
  gets that date. The scanner writes both for every file it reads, and the hourly LMS sync
  recomputes the whole library first (writing only what changed -- this is the backfill, no
  deploy-time data migration) and then pushes both into each server. `getSpotifyTracks` and
  `getSongs` take `form` (unknown values are refused) and `year` now uses the performance date for
  live sets, in both LMS query builders (`find_advanced` and `find`); `/api/library/advanced` and
  the analytics take `form` and compare `year_min`/`year_max` against the same filing year. The
  sets view has a new **Soort** filter (Sets & mixes / Livesets / Podcasts), on the phone and in
  the browser. Design: `docs/designs/track-form/`.
<!-- release notes -->
- **New Soort filter in the sets view: sets & mixes, live sets or podcasts.** A live set now also
  shows up under the year it was played, not the year it was uploaded, when MuMa knows the
  festival edition.
