# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **A spoken genre now finds all of its music, not whichever spelling the server listed first.**
  Asking for hardstyle came back with nothing at all, even though the request had been understood
  correctly and the library holds twenty thousand hardstyle tracks. The library stores a genre
  under every casing its tags have ever carried — "Hardstyle", "HARDSTYLE" and "hardstyle" are
  three separate entries — and MuMa kept whichever one came back first. That happened to be a
  leftover holding four long mixes, so a request for songs found none of them. A spoken genre now
  carries every spelling the library has of it. A genre that merely contains the spoken one, like
  "Mainstream Hardstyle", is still left out of it.

## [6.17.1] - 2026-08-20

### Fixed
- **MuMa Voice no longer closes the app the moment it finds something to play.** The screen
  parsed the request, searched the library and then died on the very last step, which made it
  look like the search had failed when it had actually succeeded. The player is tied to the
  screen that hosts it and this one was asking the wrong place for it; because that question is
  only asked when there is music to start, everything up to that point looked healthy.

## [6.17.0] - 2026-08-20

### Added
- **MuMa Voice: a microphone in the app, on the same pipeline as the car.** Tap the microphone
  in the toolbar and say what to play. The words go through the very parser and query engine
  Android Auto uses, so a phrasing that works in one works in the other. The recogniser hands
  back several readings of the same sentence and MuMa tries them in order, which is what gets
  past "hard style" for "hardstyle" without anyone noticing. There is a text field on the same
  screen for trying a phrasing without talking.
- **A question instead of a guess, where a name means more than one thing.** "Speel
  Thunderdome" can be the label, the album or the playlist. MuMa Voice now shows the readings
  and asks which one you meant; the answer can be tapped or spoken ("het label"). Android Auto
  cannot ask — there is no way back through a media session — so in the car it takes the
  strongest reading and records the ones it discarded.
- **Albums, playlists, track titles and star ratings can be spoken.** "Speel album
  Thunderdome af", "speel de afspeellijst zomer af", "speel het nummer dragonborn af", "speel
  hardstyle met minstens 4 sterren af". Two values of the same kind work too: "speel hardstyle
  en hardcore af" is one query, while "drum and bass" stays one genre.
- **Voice diagnostics, under About.** Every voice request now leaves a full trace: which
  callback it arrived through, the query exactly as received, every extra Android sent with it,
  the tokens, which parser rule claimed which word, what the library said about each term, and
  the request that finally went out. The last fifty are kept and can be shared as text. This is
  how to find out what Google rewrites before MuMa is ever called.

### Fixed
- **A spoken title is searched for by its title, not by the whole sentence.** When no filter
  matched, the fallback search was handed the entire utterance, so "speel het nummer dragonborn
  af" looked for exactly that and found nothing. It now searches for "dragonborn".
- **A spoken rating no longer drags in every unrated track.** The server widens a lone minimum
  rating to include everything nobody has rated, so a floor is now always sent with a ceiling.

## [6.16.0] - 2026-08-19

### Added
- **The appearance setting now picks a whole style, not just an accent colour.** It used to
  offer Green and Blue, which swapped one highlight colour and left everything else identical.
  It now offers **Spotify** and **MuMa**. Spotify is the app exactly as it looked before. MuMa
  keeps the same green for songs and blue for sets, but sits on a warmer, deeper background,
  separates list rows with a hairline instead of floating them as cards, dims third- and
  fourth-rank text properly instead of painting everything the same grey, rounds corners more
  tightly, dims its field labels instead of colouring them green, and colours a filled rating
  star gold. Spotify stays the default, so nothing changes until you switch, and switching takes
  effect immediately. The Blue accent is gone; the blue app icon is a separate setting and is
  unaffected.

### Fixed
- **A selected track row no longer changes shape.** The selected background was rounded to 8dp
  while the unselected one was 16dp, so a row visibly snapped when you picked it.
- **The dropdown box is no longer a white slab with invisible text.** It was still painted for
  a light theme the app has not had since before the rebrand: white fill, grey border and black
  text, on a black screen.

## [6.15.0] - 2026-08-19

### Added
- **The voice search understands a whole request, not just a genre.** "Speel willekeurige
  favorieten uit 2023 af" used to reach the free text search, which only knows artist, album and
  track names, and answered a sentence like that with silence. The utterance is now taken apart
  into the pieces the library can filter on -- a genre, an artist ("van headhunterz"), a label
  ("label art of creation"), a year ("uit 2021"), the favourites, songs or livesets -- and an order
  on top of it: "willekeurig" shuffles, "recent" plays by release date, "recent toegevoegd" by the
  date the library caught up. They combine freely, in Dutch and in English, and each part is
  optional: "speel recent af" plays the whole library by release date.

  Every spoken name is resolved against the library before it is sent, because the server answers
  a filter value it does not know with an error rather than with an empty list -- one misheard word
  would otherwise cost the whole request. A term the library cannot place is dropped and the rest
  still plays, so "speel zwabberkore uit 2021 af" plays 2021. When it can place nothing at all, the
  ordinary search takes over and looks for the title, which is what keeps "speel headhunterz af"
  finding the track of that name rather than everything the artist ever released.
- **A page listing what the voice search understands**, reachable from About. None of the wording
  above is discoverable by talking to the car and hoping.
- **A filtered track list can be re-sorted from the list itself.** Opening a genre, label,
  festival, year, podcast, line-up or rating navigated with `sortMethod = "DateDescAndRelease"`
  baked into the directions, and `list_layout_track` carried no filter bar, so
  `TrackCollectionFragment.setOrderType` was unreachable code. The screen now shows the same
  `FilterButtonBar` the album and artist lists use, offering the web UI's song sorts: recently
  released, recently added, most played, recently played, by rating, by name and random. The bar
  opens on whatever sort the caller navigated with, so an untouched list is unchanged. It stays
  hidden for albums, playlists, shares and podcast channels, whose order is the server's own
  (disc and track number, playlist sequence), and offline, where the list comes from the cache.
  "Starred" is deliberately absent: the server maps it to `t.starred_date`, a column
  `Track::find_advanced` never selects, so asking for it fails the request.

### Fixed
- **The car library listed "Favorieten" twice.** Two separate root entries carried the same Dutch
  label: the starred songs (`main.songs_starred`, "Starred" in English but "Favorieten" in Dutch)
  and the folder holding the favorite genres and tiles (`favorites.title`). In the car they were
  indistinguishable, and which one held what was a guess. The root now shows a single Favorites
  folder, with the starred songs inside it as "Favoriete nummers" next to the favorite genres and
  playlists. The folder is always present, since starred songs no longer depend on a genre or tile
  being marked; the genres and playlists entries still only appear when something is marked.

## [6.14.2] - 2026-08-19

### Changed
- **A spoken genre is sorted by release date, not by the date it was added.** Asking for a genre out
  loud is asking what is new in it. The voice search ran the browse tree's query with `AddedDesc`,
  which answers a different question: when the library caught up. A back catalogue import lands a
  hundred tracks from twenty years in one afternoon, and all of them outranked a release from last
  week. The search now uses `OriginalDateDescAndRelease`, the same sort as the "Recent uitgebracht"
  home section. A track with no release date falls back to its file date and sorts to the back
  rather than dropping out, which matters while the release date backfill is incomplete. The browse
  tree under Genres is untouched and still sorts by date added.

## [6.14.1] - 2026-08-18

### Fixed
- **A spoken genre no longer needs the word "genre" to survive the trip.** The parser only ever
  recognised a genre request by that word -- and Assistant strips it precisely when it understood
  the request as a genre one, so "speel het genre mainstream hardstyle af" arrived as "mainstream
  hardstyle" and went straight to the free text search, which matched an album instead. An
  utterance that carries no genre wording is now offered to the genre lookup as a name in its own
  right, and plays that genre when it matches one of the library's genres outright. Anything short
  of an outright match stays on the free text search, so a title that merely resembles a genre is
  unaffected. Addressing the app ("... af op MuMa") is stripped along with the other trailing
  wording, which it never was before.

## [6.14.0] - 2026-08-18

### Added
- **"Speel genre hardstyle af" plays that genre.** The voice search only ever ran the free text
  search, which matches artist, album and track names -- a genre matches none of them, so a spoken
  genre left the car silent or on some unrelated album. A spoken genre now runs the same query the
  browse tree runs: the most recently added tracks of that genre, capped at the maximum number of
  songs from the settings, every rating included. The genre Assistant hands over in the search
  extras is used when it is there, and the utterance itself otherwise -- "play genre hardstyle" and
  "speel genre hardstyle af" both land. Saying "sets" or "livesets" ("speel hardstyle sets") picks
  the livesets instead of the songs. Speech recognition splits and pads names, so "hard style" and
  "tech house music" still find their genre; a genre the library does not know falls back to the
  free text search unchanged.
- **"Play X next on MuMa" queues that song instead of replacing the queue.** Assistant exposes no
  queueing verb to third-party media apps: "add X to MuMa" is refused inside Assistant itself and the
  session is never called. The only door it opens is a play request carrying free text, so the queue
  instruction now travels inside that query as a marker word -- "speel X hierna af op MuMa", "play X
  next on MuMa" -- and is read back out on arrival. The resolved song is inserted into the queue
  rather than pushed onto the player separately, because Media3 hands the returned list straight to
  `Player.setMediaItems` and a shorter list would discard the rest of the queue. Markers are matched
  only at the tail of the query, keeping titles like "The Next Level" intact, and a query that is
  nothing but a marker falls back to the old play-from-search path.

## [6.13.2] - 2026-08-18

### Fixed
- **"Play all" in the car plays in order again.** `shuffleModeEnabled` is sticky player state: once
  shuffle play ran on the phone it stayed on until it was toggled off again, and the Android Auto
  browse tree never touched it. A queue started from the car inherited it, on exactly the drives
  that followed a shuffled listen on the phone -- which is why it looked intermittent. Both paths
  that start a queue from the car, a browse tap and a voice search, now clear the flag. Queues added
  from the phone are unaffected, and the car's own shuffle button still reorders the queue in place.

## [6.13.1] - 2026-08-18

### Changed
- **The grid records the place, never the album underneath it.** A queue with no list behind it --
  one started from Android Auto, from the notification, or restored on startup -- used to record the
  album of whatever was playing. That is not a place you went to, and out of a genre list it was
  actively wrong: playing a Raw Hardstyle track wrote down the compilation it was released on. Such
  a queue now records nothing. An album screen still records its album, because that is where
  playback started.

### Fixed
- **A genre, label, festival, podcast or year list is finally recognised as itself.** Every browse
  screen carries its tag in its filters rather than in a named argument, and the play history only
  read the named ones -- so those screens looked source-less and fell through to the album. Playing
  out of Raw Hardstyle now records Raw Hardstyle, and playing out of Art of Creation records the
  label.
- **"Play now" on a single song records the list you played it from.** Only the play button of a
  list announced the screen behind it, so playing one track out of Raw Hardstyle through the song
  menu recorded the compilation that track happens to sit on -- Dirty Workz rather than the genre.
  "Play next" and "Play last" still leave the source of the running queue alone.
- **A shortcut now appears the moment you press play.** It was written when a track scrobbled, and
  a scrobble is only submitted once a track plays out, so starting a list and skipping through it --
  or listening to half of one song -- left the grid untouched. Filling the queue is what records it
  now.
- **"Recently played" stopped changing.** The list a queue came from was remembered permanently
  rather than per queue, so the last browse screen you played from stayed the source of every later
  play -- from the home lists, from search, from the notification, from the car. The grid recorded
  that same shortcut over and over and never moved. A source now belongs to the one queue it was
  armed for, and a queue with no list behind it records nothing.
- **Shortcuts lost their artwork.** An album or a playlist shortcut was stored without the id its
  cover is keyed by, so the grid drew a placeholder where it used to show the sleeve. A genre, a
  festival, a label and a podcast have no cover of their own and now borrow one from a track that
  carries the tag, the way an artist already borrowed its picture -- one lookup per shortcut, kept
  in the stored card.

## [6.13.0] - 2026-08-17

### Added
- **Recently released and Recently added, as lists you can read.** The home screen now ends in two
  track lists instead of carousels of albums and artists, each with a "Show more" that opens the
  full list under the same sort. A carousel card is identified by its cover art, and the SoundCloud
  and YouTube part of the library has none, so a strip of blank squares said nothing where a row
  naming the title and the artist always does.
- Two new settings under the home section: how many shortcuts the grid shows (2 to 10, default 8)
  and how many rows each track list shows before "Show more" (1 to 10, default 5).

### Changed
- **"Recently played" now remembers where you played *from*.** It used to fill up with everything
  you opened, so browsing polluted it and the album of a single song you tried pushed everything
  else out. A shortcut is now written when you press play, and what it points at is the list the
  queue came from: play one track out of Raw Hardstyle and the shortcut is Raw Hardstyle. Tapping it
  later re-runs that query, so you get different tracks from the same corner of the library rather
  than a replay. Shuffle-all, starred lists and shared links record nothing -- there is no query
  behind them to re-run.
- Memories is a single banner row rather than a carousel of years, summarising the nearest year and
  disappearing entirely on a day that holds nothing. Every year is still listed in full on the
  Memories screen, one tap away.

### Removed
- The "Recently updated" section. Rewritten metadata is something the scanner does, not something
  worth listening to.

## [6.12.0] - 2026-08-17

Written after the fact. Release 0.11.0 bumped versionCode/versionName to 265/6.12.0 without adding
the matching entry here, so this section reconstructs what that build actually shipped.

### Changed
- **A track shows its original release date rather than the date of the edition it came in.** The app
  already formatted and displayed one release date; it simply never received the original one. The
  choice is made at the API boundary rather than carried through the domain model, because
  `MusicDirectory.Child`, `Track`, `Album` and every view showing a date would each have needed a
  second field saying the same thing. A year-only original never beats a full edition date, so
  precision is not traded away.

## [6.11.0] - 2026-08-07

### Added
- **Two accent colours, and a launcher icon you pick separately.** Settings → Appearance now has
  an accent colour, green or Ultrasonic indigo, and an app icon in the same two colours. They are
  independent: an indigo accent with the green icon is a perfectly ordinary combination. Sets mode
  keeps its own colour in both themes, so the two modes never blur into one another.

### Changed
- The theme setting used to offer Day & Night, Dark and Black, all three of which resolved to the
  same black theme. It picks the accent instead. An existing installation keeps green.
- The download and playback notifications show the MuMa equalizer mark. They were the last two
  places still showing the Ultrasonic headphone.

## [6.10.0] - 2026-08-07

### Added
- **Tapping the playing track opens a track info sheet.** The player's options menu carried seven
  entries that all acted on the one playing track — go to artist, go to album, show metadata,
  lyrics, share song, refresh track and the two bookmark items — buried behind an overflow menu
  that is otherwise about the queue. Tapping the title block now opens a sheet with the cover on a
  blurred backdrop of itself, the five star rating, artist and album as rows that navigate, the
  remaining actions as buttons, and genre, track number, release date and duration underneath, with
  the technical details folded away. Long-pressing the path copies it.

### Changed
- The now-playing options menu is down to what acts on the queue or the player.
- Rows the track cannot fill are hidden instead of rendering `Year: ` with nothing after it, which
  the metadata screen this replaces did. That screen, its layout and the navigation action to it are
  gone; the playlist's long-press *Show metadata* opens the same sheet.

## [6.9.2] - 2026-08-05

### Changed
- **The app is called MuMa, and it has its own icon.** "Mobile" is gone from the launcher name, the
  notification channels and every screen — the phone app and the web app are one product and now
  say so. The launcher icon is no longer the inherited headphone on indigo but MuMa's own mark:
  five bars in a green disc whose top edge traces an M, shipped as an adaptive icon with a round
  variant and a monochrome layer for themed icons. `applicationId` is unchanged, so this installs
  over the previous version.

### Fixed
- **"Onlangs afgespeeld" now remembers what was played.** The home grid only ever recorded items
  you *opened* on a browse screen, on the assumption that playing something implies having opened
  it first. That assumption does not hold for a session driven from Android Auto, the notification
  or the play queue, so an evening of listening in the car left the grid showing whatever was last
  tapped by hand. The same rebuild also deleted the only writer of the "Last played genres" lists
  while leaving the Android Auto browser reading them, so those two lists had been permanently
  empty. Both are written again, now from one place: every scrobble records the played album into
  the home grid and its genres into the per-mode genre lists.

## [6.9.1] - 2026-08-05

### Fixed
- **Checking for updates finds new versions again.** The rename carried into the uploaded APK's
  filename, and apk-hoster derives an app's series from exactly that prefix — the upload itself
  sends only the file and its notes. The app asks for the series by name
  (`/api/version?apk=ultrasonic`), so builds published as `muma-mobile-*` went somewhere no
  installed app looks: 6.9.0 was invisible and every phone reported itself up to date. The
  filename prefix is pinned again through `APK_SERIES` in `scripts/publish.sh`, separately from
  the app's own name. Renaming the series later takes two releases: first a build whose
  `UpdateChecker` asks for `muma-mobile` and falls back to `ultrasonic`, then the flip once that
  build is everywhere.

## [6.9.0] - 2026-08-05

### Added
- **Albums carry a rating.** The app only stored a favorite flag for an album, which synced
  nowhere. Albums now have a 0-5 rating like tracks, and the star on an album row toggles rating 5.

### Changed
- **Rating 5 is what favorite means; the separate favorite flag is gone.** The heart/star toggle in
  track rows, the dedicated favorite button in the player and its overflow menu entry are removed,
  and the five star display is always on screen. The hardware STAR key toggles rating 5. The
  Favorites screen keeps its place: the server answers it with whatever is rated five stars.

## [6.8.0] - 2026-08-05

### Added
- **Pick how many tracks a genre opens with, from the genre screen.** Opening a genre always
  fetched the same number of tracks, and the only way to change it was a preference several
  screens away, which is the wrong place for a choice that changes per visit. The genre grid now
  carries a dropdown — 10, 25, 50, 100 or 500 — and the next genre you open uses it.

### Changed
- **Renamed from Ultrasonic to MuMa Mobile.** The launcher name, notifications and in-app text now
  read "MuMa Mobile", the Kotlin package moved from `org.moire.ultrasonic` to
  `nl.teunschriks.mumamobile`, and the Gradle module from `:ultrasonic` to `:app`. `applicationId`
  is unchanged, so the update installs in place and keeps every server, setting and download.
  **Home-screen widgets must be removed and re-added once**, because launchers store the widget's
  old class name. Broadcast actions, media-session custom commands and notification channel IDs
  keep their historical `org.moire.ultrasonic` values on purpose — they are cross-process contracts,
  and `RuntimeContractTest` fails the build if one of them changes.
- The built-in server entry is now labelled "MuMa" rather than "LMS"; the old stored name is still
  recognised so upgraded installs match it.

### Fixed
- **The rating button in Android Auto always gave one star.** A track rated 5 dropped to 1, a track
  rated 1 stayed at 1, and an unrated one became 1 — no other rating could be reached from the car.
  Each button carries the rating it was drawn with in its `SessionCommand` extras, and the tap
  handler cycled on from there, but a tap made in the car comes in over the legacy session, where
  media3 builds a fresh `SessionCommand(action, Bundle.EMPTY)` and hands the received bundle to the
  separate `args` parameter — and `MediaControllerCompat` sends only its caller's bundle, never the
  custom action's own extras. The rating therefore read as its default of 0 and every tap cycled to
  1. The playing track, which is what the button was drawn from, now decides; the extras are only a
  fallback. `MediaItem.setUserRating` also records the rating in the item's metadata, so the ten
  minute track cache expiring on a paused or long track no longer brings the old rating back, and a
  rating given on the phone now redraws the car's button.
- **The genre track limit in Settings did nothing.** The preference stored its value under
  `genreTrackLimit` while the code read an integer under `genre_track_limit`, so opening a genre
  always used the built-in 100 no matter what was set. Both now read and write the same
  preference.

## [6.7.0] - 2026-08-03

### Added
- **A three-line track row.** Album and artist shared one line, so a slightly longer title pushed
  both into an ellipsis and neither could be read. Settings > Appearance now offers a three-line
  row — title, album and artist stacked, with the stars, release date and duration on the right —
  next to the compact two-line row, which stays the default and looks exactly as it did.

### Fixed
- **The Beheer tab was hidden from admins.** The admin check calls `api/auth/verify`, which sits
  under the `/api/auth/` prefix the Muma interceptor treats as needing no key, so the request went
  out unauthenticated: 401, an empty body, `isAdmin` false for everyone. The interceptor now lists
  the four credential endpoints explicitly instead of matching a prefix, and the visibility check
  re-runs on resume and after the auto-login has fetched a key — the `onCreate` check ran before
  either had happened.
- **Rotating the screen duplicated the playlist.** A configuration change closes the Koin activity
  scope, so `MediaPlayerLifecycleSupport` is rebuilt with `created = false` and the recreated
  activity's `onResume` restores the serialized session with `InsertionMode.APPEND` — on top of a
  playback service that survived the rotation with the playlist still loaded. `restoreLastSession`
  now returns early when the player already holds tracks; the `afterRestore` callback still runs,
  so the media button intents that wait on it keep working.

## [6.6.0] - 2026-08-02

### Added
- **Memories: what was released on this day, in earlier years.** The Library tab has a Memories
  screen, and the home screen opens on a short row of "Today, 8 years ago" cards, both fed by the
  new `/rest/getMemories` endpoint. Only tags carrying a complete release date can answer for a
  given day, so year-only tags never appear; a day with no exact match widens to three days either
  side and says "this week" rather than claiming a precision the tags do not have. The device
  sends its own date, so a phone in another time zone gets its own today. The home row can be
  switched off in settings.
- **Diagnostics can be sent without waiting for a crash.** Crash reporting only fired on the next
  app start, and only after the app had actually died, so the failures that leave the app running
  — a call that returns an error, a screen that stays empty — never reached the server. Settings
  now has "Send diagnostics now" under the Muma section, which uploads the current session's log
  and writes a copy to Downloads/UltrasonicLogs. It sits outside the debug category on purpose,
  because that category is hidden in release builds. Unlike the automatic report it ignores the
  "Crash detection" toggle — pressing the button is consent — and it never deletes a crash file
  that hasn't been reported yet. Manual reports are marked as such in `crash_reports`, so they
  are distinguishable from real crashes and from silent kills.

### Changed
- **The Ratings and Years tabs no longer offer a search field.** Ratings is five fixed cards that
  are all on screen at once, and Years is a short list of numbers in a known order, so the shared
  filter bar's search box only took room the cards could use. Years now leads with the newest year
  instead of sorting by name.

### Removed
- **The "MuMa Sync" screen** and its six buttons (log on, load/write tiles, clear tiles,
  load/write settings). Tiles already sync through the tile editor and the log-on step already
  happens when a server is saved; the settings backup/restore pair was a blunt dump of every
  shared preference that needed a restart and could overwrite a working install with another
  device's state. The MuMa user ID and API key settings stay.

### Fixed
- **An artist shortcut keeps the blank it was saved with.** A shortcut stored while the server had
  no picture for that artist holds an empty cover art id, and an empty id never asks for a picture
  at all. Such a card now has its artwork looked up once and the stored copy repaired; the index
  conversion also stored an empty string where the artist conversion stored nothing, so a missing
  id looked usable downstream. Both now agree.
- **A cover art the server does not have is not re-requested on every bind.** Artists with no
  artwork anywhere cost one failed request per card each time the home screen scrolled back into
  view. Their ids are remembered for twelve hours, per app run, and only when the server actually
  answered "not found" - a timeout, a 5xx or being offline says nothing about whether the picture
  exists.

## [6.5.26] - 2026-08-02

### Changed
- **The Android Auto star button sets a rating instead of a favourite.** It toggled the Subsonic
  favourite flag; it now cycles the track's five-point rating through six states — an empty star
  for no rating, then a star carrying the digit 1 through 5, wrapping back to empty. Ratings are
  what the rest of the app acts on: the track list sorts and filters by them and the player has a
  five-star widget, but none of it was reachable from the car. Each of the six buttons carries the
  rating it was drawn with, so a tap derives the next rating from the button itself rather than
  from state that can go stale between track changes. Favourites still work everywhere on the
  phone; keeping both buttons in the car would have pushed shuffle and repeat into the overflow
  menu.

## [6.5.25] - 2026-08-02

### Added
- **The artist page opens with the artist rather than with a list.** Tapping an artist used to
  land straight on their albums, with the name in the app bar the only thing distinguishing one
  artist from the next — even though the app already downloads and caches artist images and
  already shows the album and track counts one screen earlier, in the artist list. The page now
  starts with a header: the artist image, the name, "12 albums · 143 tracks", the years the
  discography spans, and the genres. The play-all button moved into it and queues the artist's
  tracks the same way the long-press menu's "play now" does. Artists reached through search or
  from a home screen card never went through the cache that holds the counts, so the header
  derives them from the discography on screen instead of showing nothing.
- **Labels are browsable.** The filter modal could already narrow songs down to a record label,
  but nothing showed which labels the library holds — you had to know the name before you could
  filter on it. Labels now sit in the Library tabs next to Genres, fed by the same PUBLISHER tag
  the filter chip uses, and a tap opens that label's tracks.
- **Sallaands and Brabants**, the same two dialects the web interface picked up in 0.0.59, chosen
  from the language menu that was already in Settings. Neither dialect has a language code, so
  they ride along on Dutch with a region no Dutch speaker has set: nl-BQ and nl-CW. Three other
  shapes were tried first and none of them survive Android's resource matching — a three letter
  code (nds-NL) and a BCP 47 variant (nl-NL-brabant) both fall back to the default, and any
  locale missing from `resourceConfigurations` is stripped from the APK before it ever reaches a
  device.

### Fixed
- **The folder selector no longer sits squeezed into one column** when an album list is switched
  to the grid layout. It was laid out as a single album-sized cell with the first two albums
  beside it; headers now span the full width of the grid.
- **Dutch is complete, and English is actually English.** The Dutch resources were 163 strings
  short of the English ones, and 28 strings this fork added were written in Dutch in the default
  resources — so an English-language phone showed "Artiesten", "Jaren" and "Goedkeuren". Both are
  filled in now, which the dialects depend on: Android treats nl-BQ and nl-CW as Dutch, so a gap
  in Dutch falls through to a dialect rather than to English.
- **Artists without a fetched picture are no longer grey.** Server-side change: an artist whose
  image the fetcher does not have yet is now served their scanned artist image, or the cover of
  their earliest release, instead of a 404.

## [6.5.24] - 2026-08-01

### Added
- **Search and sort on the Library tabs.** The Artists and Albums tabs gained a search field and a
  sort selector; artist search runs server-side over the whole library through new `query`/
  `sortBy` parameters on `getArtists.view`, which also reports `songCount` per artist. Albums
  reuse the `query` parameter `getAlbumList2.view` already accepted and gained a `byTrackCount`
  order. The Genres, Years, Festivals, Lineups and Ratings tabs filter and sort their already-
  loaded cards in memory, diacritic-insensitively. Artist rows now show album and track counts.

### Fixed
- **Tapping an artist opened a blank screen.** The artist list and the home screen's artist cards
  navigated to `artistDetailFragment`, whose `ArtistDetailFragment` was never more than a stub: a
  bare `Fragment` with no layout and no data loading, so it rendered nothing. Both now open the
  artist's album list - the same destination search results and the player's "show artist" have
  always used. The unused fragment and its navigation destination are gone, and the destination is
  now covered by a unit test so a blank artist page cannot come back unnoticed.


## [6.5.23] - 2026-08-01

### Fixed
- **The About screen still linked to upstream Ultrasonic.** "Visit webpage" opened
  `ultrasonic.gitlab.io` and "Report a bug" opened `gitlab.com/ultrasonic/ultrasonic/issues`,
  both inherited from the project this app was forked from. They now open
  `https://muma.example.com` and this project's own issue tracker.

## [6.5.22] - 2026-08-01

### Fixed
- **Opening Settings crashed the app.** `SettingsFragment` sets every list setting's summary to
  the selected entry, and `ListPreference.getSummary()` feeds that summary through
  `String.format()` to substitute the entry into it. The interface size options added in 6.5.21
  are the first entries in the app that contain a literal `%` ("100%", "75%", ...), so binding
  that row threw `UnknownFormatConversionException: Conversion = '%'` and killed the process.
  The `%` is now escaped. This affected every install rather than only upgrades: the preference
  persists its default value while the screen inflates, so the summary is applied the very first
  time Settings is opened.

## [6.5.21] - 2026-08-01

### Added
- **Radio (beta) in Android Auto.** A "Radio" entry in the car's browse tree lists the channels the
  server offers; picking one tunes into a shared programme that is already playing, mid-track, in
  sync with everyone else listening. The server owns the timeline, so the app measures its clock
  offset against the server and corrects drift with a small playback-rate nudge rather than
  stuttering seeks. Skip and seek are removed from the player commands while a channel is on air, so
  the car greys them out instead of letting a tap fight the sync loop.
- **An "Interface size" setting under Appearance, defaulting to 75%.** The layouts hardcode their
  dp values instead of using dimension resources, so there was no single place to make the UI
  denser. `UiScaleHelper` now wraps the activity's base context with a scaled `densityDpi` — the
  same mechanism as the system's "Display size" — which shrinks every dp and sp at once. At 75% the
  album rows land at ~64dp with 48dp artwork and 13.5sp titles, instead of ~86dp with 64dp artwork
  and 18sp titles, which is roughly Spotify's list geometry. Selectable between 100% and 70%;
  changing it recreates the activity through the existing theme-changed event. Note that at 75% a
  48dp touch target renders as 36dp, below the accessibility minimum, which is why the setting can
  be turned back up.
- **Favorite genres, shared with the web player.** Long-pressing a genre in Library → Genres opens a
  context menu that adds or removes it; favorites are drawn with a star and sorted above the
  recently-picked ones. The list lives in the same place the web UI keeps it — the MuMa per-app
  settings blob under `app_id = "frontend"`, key `favoriteGenres` — so both clients see one list.
  `FavoriteGenres` (in `home/`) reads and writes it through the existing generic
  `getMumaSettings`/`saveMumaSettings` calls, merging into the blob so keys the web UI owns survive,
  and keeps a local copy in `Settings.favoriteGenres` so the list works offline and on Android
  Auto's thread. A push that fails is logged and retried by the next toggle; the local edit is never
  lost.
- **A Favorites folder in Android Auto**, with a Genres and a Playlists subfolder. A favorite genre
  plays straight from the folder — no year or sort-method level in between — and the playlists
  subfolder holds the dynamic playlists whose star is set in the filter modal, which is the first
  thing `TileInfo.favorite` is actually read for. Root and subfolders only appear when they have
  content, and both sources are local, so the root request still makes no network call.

### Changed
- **Default song/liveset tiles are now era-specific instead of plain genre tiles**: the eight
  single-genre defaults (Euphoric Hardstyle, Hardstyle, Mainstream Hardstyle, Raw Hardstyle,
  Hardcore, Mainstream Hardcore, Uptempo Hardcore, Bouncy Uptempo) duplicated the genre list,
  which reaches the same result on its own. Replaced by three genre + year-window tiles the genre
  list cannot express: Hardstyle Classics (Mainstream Hardstyle, 2009-2017), Millennium Hardcore
  (Mainstream Hardcore, 2010-2015) and Early Uptempo (Uptempo Hardcore, 2012-2017), all randomly
  sorted. Year lists are enumerated per year because the server resolves `YEAR` filter values to
  exact clusters and has no range support. Applies to fresh installs without server-side tiles;
  existing installs keep their stored tiles.
- **Crash detection is now an opt-in setting, off by default** (Settings > Debug options > Crash
  detection). It infers a crash whenever the previous process did not reach the clean-shutdown
  path, and Android kills the process on ordinary exits often enough that this reported a "crash"
  after almost every session. With the setting off, the evidence is still collected at startup but
  never turned into a report, a dialog or an upload; switching it on restores the previous
  behaviour from the next crash onwards. The setting is read when the main Activity starts rather
  than during application creation, because preference keys come from resources.

## [6.5.20] - 2026-07-31

### Added
- **A "Log out" entry in the toolbar overflow menu.** Signing out previously meant clearing the app
  data or reinstalling. It confirms first, stops playback, clears `Settings.staticPassword`, the
  MuMa API key/user id and the encrypted MuMa tokens, resets the music service, and reopens the
  welcome/login dialog with the username prefilled. Downloads are untouched.
- **Skeleton placeholders on the home screen.** `HomeSectionState` gives every section its own
  Loading/Empty/Content state, so each slot shows pulsing placeholders
  (`home_skeleton_carousel`/`home_skeleton_grid`, `@anim/skeleton_pulse`) until its own data
  arrives instead of the whole screen staying black until the slowest section finished. A reload
  keeps sections that are already on screen.

### Changed
- **The home screen loads concurrently.** `HomeViewModel.load()` launches one coroutine per
  provider and publishes each section as it completes, and `LibraryActivityProvider` fetches its
  artists, albums and labels/festivals with `async` instead of one after another — six sequential
  round trips became two rounds of three parallel ones.

### Fixed
- **A password rejected mid-session returns to the login screen.** Subsonic error 40 was only ever
  turned into a message by whichever screen happened to make the call, so a password changed on the
  server left the app permanently broken with no way back to the login screen.
  `AuthenticationFailureNotifier` (in `core/subsonic-api`, called from both `throwOnFailure()`
  overloads) now reports it, `UApp` republishes it on `RxBus`, and `NavigationActivity` ends the
  session and shows the login screen with an explanation. Only error 40 does this: errors 50 (not
  authorized) and 70 (not found) leave the session alone.

## [6.5.19] - 2026-07-31

### Fixed
- **Release builds crashed with `IllegalArgumentException: class com.google.common.reflect.TypeCapture
  isn't parameterized` whenever a track's genre list was deserialized**: the Room `Converters`, the
  `MediaItem.toTrack()` converter and `TileStorage` built their Gson type via an anonymous Guava
  `TypeToken` subclass. Guava ships no consumer ProGuard rules, so with
  `android.enableR8.fullMode=true` R8 merged away the parameterized superclass those tokens read at
  runtime. This fired on `onTimelineChanged`/`onMediaItemTransition`, i.e. on nearly every playback
  start, and only in release builds — it accounts for 15 of the 16 crashes collected on 6.5.14
  through 6.5.18. All three sites now deserialize through `Array<T>::class.java`, which needs no
  runtime generic signature. Keep rules for the Guava `TypeToken` hierarchy were added as a second
  line of defence. The Gson `TypeToken` usages elsewhere are unaffected: Gson ships its own consumer
  rules.
- **Errors reported while no Activity was available took the whole app down**: `InfoDialog`/
  `ErrorDialog` built their `MaterialAlertDialogBuilder` in the constructor, outside the existing
  try/catch, so a non-AppCompat context — such as the application context handed to a background
  coroutine's error handler — threw "The style on this component requires your app theme to be
  Theme.AppCompat". The builder is now created lazily against a themed context, and falls back to a
  toast if the dialog still cannot be shown.
- **An exception thrown inside any RxBus subscriber killed the process**: none of the subscribers
  pass an `onError` handler, so RxJava rethrew as `OnErrorNotImplementedException` on the delivering
  thread. A global `RxJavaPlugins` error handler now logs these instead.
- **Android Auto bleef hangen op een dode of offline serververbinding.** De mediasessie van Auto
  haalde de `MusicService` één keer op, bij het aanmaken van de sessie, en hield die instantie vast
  zolang de app draaide. Alles wat die instantie vervangt — van server wisselen, inloggegevens
  aanpassen, of `getMusicService()` die de offline service teruggeeft terwijl de server onbereikbaar
  is — liet Auto met de oude achter: de mappenstructuur werd nog gewoon getoond, maar elke lijst
  kwam leeg terug, ook nadat de app op de telefoon (die per aanroep opnieuw ophaalt) allang weer
  werkte. Auto haalt de service nu bij elke aanroep opnieuw op.

## [6.5.18] - 2026-07-31

### Added
- **Beheer-tab**: onderin is er een vierde tab bijgekomen die de beheerpagina's van de webui
  spiegelt. Voor nu: Downloaders (SoundCloud-accounts en YouTube-kanalen), Gebruikers (bekijken,
  in- en uitschakelen) en Verzoeken (goedkeuren, terugdraaien, afwijzen). De tab is alleen zichtbaar
  als je beheerder bent.

### Added
- **Vier tabbladen erbij in Library**: Jaren, Festivals, Lineups en Ratings, naast Playlists,
  Genres, Artiesten, Albums en Opgeslagen. Zoeken op lineup kan daarmee weer.

### Changed
- **In sets-modus tonen de carrousels op de startpagina festivals in plaats van labels.** Livesets
  zijn festivalopnames, dus een platenlabel zegt er weinig over.

## [6.5.17] - 2026-07-31

### Fixed
- **Een artiest aantikken op de startpagina leverde niets op.** De carrousels bevatten ook remixers
  en gastartiesten zonder eigen albums, waardoor je op een leeg scherm belandde. Er staan nu alleen
  nog artiesten met eigen releases in.
- **Een label aantikken leverde niets op.** De labels kwamen uit een andere tabel dan waarop
  gefilterd wordt, dus zoeken op zo'n naam gaf nul resultaten. Beide gebruiken nu dezelfde bron.
- **Artiestafbeeldingen op de startpagina** worden weer onder de juiste sleutel en op groot formaat
  opgehaald, zodat ze gedeeld worden met de rest van de app in plaats van elke keer opnieuw geladen.

## [6.5.16] - 2026-07-31

### Added
- **Library tab**: one place for everything you browse by type — dynamic playlists, genres,
  artists, saved playlists and albums — as swipeable pages under a tab strip.

### Fixed
- **Browsing was unreachable in 6.5.15**: removing the home screen's filter chips also removed the
  only way into dynamic playlists, genres, the album list and the artist list. Creating a dynamic
  playlist was impossible, since that happens on the same screen. The Library tab brings all of it
  back.
- **The Favorieten tab showed a copy of the home screen.** It now shows starred albums, starred
  artists and everything you rated four stars or better; tapping a track plays it.

### Changed
- **Bottom navigation is now Home, Library and Favorieten.** Zoeken left the bottom bar because the
  toolbar already has a search field, and playlists moved into Library.

## [6.5.12] - 2026-07-30

### Added
- **Welcome dialog now distinguishes "server unreachable" from "login failed"**: both the manual
  username/password submit and "Sign in with Google" previously collapsed every failure into the
  same generic network-error message. Added an unauthenticated `/rest/ping.view` reachability
  probe that runs on login failure to tell the two apart.

### Fixed
- **The welcome dialog's login test could report success without ever contacting the server**:
  when "Auto-switch server online/offline" was enabled (the default before 6.5.11/version 0.0.34)
  and a `ConnectivityManager` capability check transiently/incorrectly reported no network, the
  login test silently used the no-op `OfflineMusicService.ping()` instead of actually validating
  the server/credentials. The login test now always uses the real, network-backed service.

## [6.5.11] - 2026-07-29

### Changed
- **Dependencies**: Updated `activity-ktx`, `core-ktx`, `gson`, `okhttp`, `rxjava`, and other core libraries to latest stable versions.
- **Target SDK**: Updated to Android 17 (API 37).
- **Login/auth UI**: Restyled the login/welcome dialog, edit-server screen, and Google
  access-request screen to match the web frontend: filled pill-shaped inputs, a real "Sign in with
  Google" button with the brand G logo, a proper divider, a red error banner, and colored
  info/success/error status banners for pending/rejected/approved access requests. Replaced a
  stray non-brand color in the filter dialog/search FAB with `spotify_green`, and aligned the nav
  drawer's item tinting with the bottom nav's brand colors.
- **Settings**: `autoSwitchOffline` now defaults to `false` instead of `true`.

### Added
- **Export to Media Device**: New feature to export the current playlist to external USB devices (e.g., Shokz OpenSwim Pro) via SAF. Includes an option to clear the destination folder before exporting.

## [6.5.2-232] - 2026-07-16

### Fixed
- **Update Checker**: Added `u=guest` and `p=guest` credentials to APK download URL to prevent access errors.

## [6.5.0] - 2026-07-11

### Added
- **Log Viewer**: New diagnostic tool accessible from Settings > About to view and share app logs.
- **Architecture Tests**: Integrated ArchUnit for maintaining code structure and dependency rules.
- **Coverage Reporting**: Added JaCoCo integration for automated test coverage analysis.
- **Welcome Messages**: Dynamic greeting messages based on the time of day.

### Changed
- **UI Refinement**: Wrapped main layout in a scrollable view for better accessibility on smaller screens.
- **Track Loading**: Optimized track and album loading with a centralized, state-aware repository pattern.
- **Server Selection**: Improved UX for server switching and connection validation.
- **CI/CD**: Enhanced build pipeline with pre-commit hooks and automated documentation updates.

### Fixed
- **Android Auto**: Reverted to a stable Tile-based interface to resolve navigation and performance issues.
- **Build Stability**: Fixed various compilation errors and resource conflicts in recent feature branches.

## [6.4.0] - 2026-07-05

### Added
- **MuMa Cloud Sync**: Backup entire app configuration to the MuMa database.
- **Settings API**: Integration with the new MuMa User App Settings endpoints.
- **MumaAPIClient**: Modern networking layer for MuMa interactions.
- **Sync UI**: Manual backup and restore buttons in Settings.

## [6.3.3] - 2026-07-05

### Changed
- **LMS API Key**: Replaced dynamic API key fetching with a hardcoded Subsonic API key for LMS servers for simplified setup.

## [6.3.2] - 2026-07-05

### Added
- **API Key Automation**: Automatically fetches Subsonic API keys for LMS servers during setup and connection testing.

## [6.3.0] - 2026-07-05

### Added
- **Welcome Dialog**: New users are now greeted with a setup wizard to enter login credentials.
- **Auto-Server Discovery**: Automatically configures Alpha and Stable LMS servers based on build type.
- **Connection Validation**: Real-time server ping during setup to ensure correct credentials.
- **Dynamic Playlists (Tiles)**: Support for server-side dynamic playlists synced with LMS and Music Management.
- **Debug Features**: Share and view debug logs directly from settings in debug builds.
- **ListenBrainz**: Scrobbling is now enabled by default.

### Changed
- **UI Improvements**: Significant visibility improvements to player controls, including a green pause button.
- **Landscape Player**: Optimized player layout for landscape mode with scrollable controls.
- **Tile Loading**: Delayed initial tile loading until server connection is established.
- **Deployment**: Improved APK distribution with robust fallbacks.
- **Default Settings**: 5-star rating system enabled by default.

## [6.2.0] - 2026-07-04

### Added
- **Spotify-style UI**: Integrated dynamic "Songs" (Green) and "Sets" (Blue) branding throughout the app.
- **Merged Views**: "Songs" and "Livesets" tabs merged into a single view with a brand-aware toggle switch.
- **OLED Black Theme**: Implemented a pure black (#000000) background for OLED displays and removed the light theme.
- **Brand Consistency**: Dynamic accent color updates for switches, sliders, chips, and scrollbars across all fragments.
- **Tooling Upgrade**: Modernized build pipeline with Gradle 9.6.0 and updated core dependencies.
- **Improved About Screen**: Detailed information on `muma/lms` integration and technical build details.
- **Update System**: Enhanced auto-update checker with authentication and version tracking.

## [6.0.0-140] - 2026-07-04

### Added
- Integrated full changelog support for debug builds in the distribution pipeline.
- Added direct link to `changelog.md` in the download portal.

## [5.2.1] - 2026-07-04

### Added
- Automated version increment support to `bup` script (patch, minor, major).
- Automatic synchronization of bundled assets during release.

## [5.2.0] - 2026-07-04

### Added
- Major dependency update: all libraries and Gradle updated to latest stable versions.
- Gradle updated to 8.12.1.
- Updated to AGP 8.7.3.
- Updated to Kotlin 2.1.0.
- Added `debug` and `release` build type support to the build pipeline.
- Added automatic Git tagging for `release` builds in `bup`.
- Added release notes extraction and metadata generation for APKs.

### Changed
- **Project Structure**: Migrated `apk-hoster` to a standalone repository.
- **Project Structure**: Moved all utility scripts to the `scripts/` directory.
- **Configuration**: Replaced `local.properties` with `.env` for better environment management.
- **Pipeline**: Refactored `bup` as a lightweight wrapper for `scripts/build-and-publish.sh`.
- **Pipeline**: Default build type changed to `debug`.

### Removed
- Removed Docker orchestration logic and `docker-compose.yml` (now handled in `apk-hoster` repository).

## [5.1.0] - 2026-07-04
### Added
- Created `scripts/deploy-stack.sh`, a generalized Docker stack deployment tool supporting Portainer discovery, SSH transfer, and intelligent fallbacks.
- Support for initial stack creation: the deployment script now automatically creates the stack if it does not exist yet using a local template.
- Persistent Build Directory: Configured the build system to use a shared folder (`/mnt/user/ultrasonic-builds`) for all APKs and distribution files.
- Generic Docker Image: The `apk-hoster` Docker image is now generic and uses volume mounts for content, avoiding the need to rebuild the image for every new build.
- Auto-update system: Implemented `UpdateChecker` polling `apk-hoster` API on startup.
- Integrated Changelog: Bundled `CHANGELOG.md` and `RELEASE_NOTES.md` into assets; added `Util.showChangelog` for in-app viewing.
- Version Tracking: Added `last_seen_version` to `Settings` for automated update detection and release notes popup.
- Modular build system: `build.sh`, `publish.sh`, and `deploy.sh`.
- Versioned Docker tagging: the `apk-hoster` image is now tagged with both `:latest` and the version name from Gradle (e.g., `:5.1.0`).
- Portainer Webhook support for automated Stack updates.
- Automatic Docker group permission handling via `sg docker` re-execution.
- Integrated `apk-hoster` deployment into the main pipeline.
- `bup` shortcut for full build-publish-deploy workflow.
- Registry authentication pre-checks for Docker Hub.

### Changed
- **Deployment**: Refactored `deploy.sh` to use the new generalized `deploy-stack.sh` helper, simplifying per-project deployment scripts.
- **Deployment**: Enhanced stack discovery to support `PORTAINER_HOST` for pulling master templates.
- **Deployment**: Improved robustness with `base64` template transfer and automated tab-to-space conversion in compose files.
- Migrated all build and deployment configurations to `local.properties`.
- Updated `install.sh` for automated SDK and dependency management.
- Standardized deployment variable names for cross-project compatibility.

### Fixed
- Fixed deployment failure when no existing stack configuration is found on the remote host by providing a local `docker-compose.yml` fallback.
- Fixed empty webpage in `apk-hoster` by bundling the `dist` directory into the Docker image.
- Fixed APK files downloading as ZIP by registering correct MIME types in `apk-hoster`.
- Fixed .env loading logic to skip invalid bash identifiers.
- Fixed non-interactive session hangs in `publish.sh`.

## [5.0.1] - 2026-07-02
### Added
- 'Check for Updates' button in the About screen.
### Fixed
- Patch for initial testing of updated deployment scripts.
