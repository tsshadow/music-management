# Live Radio Stations - Technical Design

Implements [`functional.md`](functional.md). Issue #213.

## Stream Addresses

Measured on 2026-11-06. All three gave `audio/mpeg`, and `currentTime` went up in headless Chromium with
`crossorigin="anonymous"` and an `AudioContext` on the element. Nothing was played on a phone or in a car.

| Slug | Name | URL | Bitrate |
|---|---|---|---|
| `slam` | SLAM | `https://playerservices.streamtheworld.com/api/livestream-redirect/SLAM_MP3.mp3` | 128 kbit/s |
| `q-dance` | Q-dance | `https://playerservices.streamtheworld.com/api/livestream-redirect/Q_DANCE.mp3` | 192 kbit/s |
| `538` | 538 | `https://playerservices.streamtheworld.com/api/livestream-redirect/RADIO538.mp3` | 128 kbit/s |

Do not use `https://stream.slam.nl/slam_mp3`. Its redirect has no `Access-Control-Allow-Origin`, so the
web player fails with `NotSupportedError`, because `Player.svelte` sets `crossorigin` on its one audio
element. A station without CORS still plays in the app, and the browser shows that it is not available.

## Data Model

A new table in `services/common/schema_tables.py`:

```sql
CREATE TABLE IF NOT EXISTS `radio_stations` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `slug` varchar(64) NOT NULL,
  `name` varchar(128) NOT NULL,
  `stream_url` varchar(1024) NOT NULL,
  `sort_order` int(11) NOT NULL DEFAULT 0,
  `enabled` tinyint(1) NOT NULL DEFAULT 1,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `slug` (`slug`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
```

The seed `services/common/seeds/radio_stations.sql` inserts the three stations only when the table has no
rows (an anti-join). `INSERT IGNORE` would bring back a removed station on each start.

The server never opens a `stream_url`, so a curator cannot use it to make the server call an internal
address.

## API Contract

No breaking change. `/api/radio/{slug}/state` has a different path shape, so the routes do not collide.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/radio/stations` | `include_disabled` (bool, default false; true needs `radio.manage`) | `{"stations": [{"slug", "name", "stream_url", "sort_order", "enabled"}]}`, by `sort_order`, then `name` | 401 no key, 403 `include_disabled` without permission, 503 no database |
| `POST /api/radio/stations` | `slug`, `name`, `stream_url`, optional `sort_order`, `enabled` | 201, the station | 403 no `radio.manage`, 409 slug exists, 400 invalid value |
| `PUT /api/radio/stations/{slug}` | `name`, `stream_url`, `sort_order`, `enabled` | the station | 403, 404, 400 |
| `DELETE /api/radio/stations/{slug}` | none | `{"deleted": slug}` | 403, 404 |

`stream_url` must be `https://` with a host. Android refuses cleartext
(`network_security_config.xml`) and a browser blocks mixed content. Other values give 400, the same as the channel routes.

## Cross-App Impact

All in one change (AGENTS.md rule 7).

**music-manager.** The routes above in `routers/radio.py`, with the existing `verify_api_key` and
`radio.manage`.

**muma-mobile.**

- `MumaAPIDefinition.getRadioStations()`.
- `StationPlaybackController` next to `RadioPlaybackController`. It sets one `MediaItem` with the media id
  `MEDIA_STATION_ITEM|<slug>` and the `https` URI. `Scrobbler.scrobbleIdFor` returns null for the `MEDIA_`
  prefix, so no scrobble needs new code. Add a test that pins this.
- `onAddMediaItems` starts the station and returns an empty list, the same as radio.
- `playerCommandsFor` withdraws the radio commands when a station plays too.
- `BrowseTabsArea` gets a row Radio before MuMa Radio and Nieuws. `FeedBrowseArea` lists the stations as playable
  items. Add the strings for each locale.
- Retry: while a station is active, `recoverFromError` in `PlaybackService` gives the error to the
  controller, not to `PlaybackErrorRecovery`. The controller loads the stream again after 2, 4, 8, 16 and
  then every 30 seconds, for 5 minutes. `STATE_ENDED` counts as the same error, because a live stream has
  no end.
- Pause: when play starts after a pause, the controller loads the stream again, which gives the live point.
- News: `NewsPlaybackController` remembers the station slug in the same way as the radio slug.
- `MumaPlayerPlugin`: `startStation({slug})`, `stopRadio()` also leaves a station, and `stationSlug` and `stationTitle` in
  `state()`.
- The ICY title: `PlaybackServiceRules.StreamTarget.Direct` keeps the Icy-MetaData header that media3 sets,
  and media3 gives the title to the session. Only the `id|bitrate|path` branch removes it. Confirm the
  car display on a device.

No MuMa credentials reach the broadcaster. The resolver sets `X-API-Key` only for news, and
`TokenRecoveryInterceptor` changes only a request with a `t` and an `s` parameter, after a Subsonic
refusal. `PlaybackServiceRulesTest` pins that an `https` address stays unchanged.

**frontend.**

- `platform/index.js`, `platform/capacitor/player.js`: `startStation`. `stopRadio` also leaves a station.
- `Player.svelte`: a store `liveStation`, and two sections in the radio menu: Radio and MuMa Radio. The existing default channel is renamed from Radio to MuMa Radio at start-up, unless a curator chose another name. In the browser, the engine
  gets `load({url, autoplay: true})`. No `radioController` runs. While a station plays, the code does
  not write a listen, does not send jam state and hides the seek bar. `reconcileNativeRadioNews` also
  reads `stationSlug`, so a station started in the car shows in the app.
- `RadioStationsSection.svelte` in `RadioTab.svelte`: add, change, disable and remove. Text in all four locales.
- `docs/styleguide.md` first, if the menu section needs a new style (AGENTS.md rule 15).

**LMS.** None. `getInternetRadioStations` stays not implemented.

**Release.** The change needs a new `versionCode`, because the APK includes the web bundle. Refresh
`tests/integration/schema/production.tsv` after the release. Add a `changelog.d/` fragment, and update
`AGENTS.md`, `docs/radio-mode.md` and `docs/api-specification.md`.

## Technical Acceptance Criteria

1. `GET /api/radio/stations` returns only enabled stations in order, and `include_disabled=true` without
   `radio.manage` gives 403. The query is in `tests/integration/test_router_sql.py`.
2. POST, PUT and DELETE give 403 without `radio.manage`, and `http://host` or `ftp://host` gives 400.
3. A second seed run adds nothing, and after a DELETE of one station the seed does not add it again.
4. `scrobbleIdFor("MEDIA_STATION_ITEM|slam")` is null.
5. A unit test on the retry timing: the delays are 2, 4, 8, 16 and 30 seconds, and it stops after 5 minutes.
6. While a station plays, `playerCommandsFor` does not include `COMMAND_SEEK_TO_NEXT`,
   `COMMAND_SEEK_TO_PREVIOUS` or `COMMAND_SEEK_IN_CURRENT_MEDIA_ITEM`.
7. Vitest: a station in the browser calls `load` with its URL and writes no listen.
8. Check on a device after the release (a `verify` issue): the three stations in the car, the title in
   the car, a connection loss of 1 minute, pause and play, and a news bulletin during a station.

## Related Docs

- [`docs/radio-mode.md`](../../radio-mode.md)
- [`docs/designs/android-auto-browse/functional.md`](../android-auto-browse/functional.md)
- [`docs/designs/playback-error-recovery/technical.md`](../playback-error-recovery/technical.md)
