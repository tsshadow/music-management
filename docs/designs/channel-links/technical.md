# Channel Links — Technical Design

Implements [functional.md](functional.md). Builds on the `channels` table from
[channel-coverage](../channel-coverage/technical.md) and on the proposal flow of
`rules_label_proposals` (`services/importer/label_proposal_store.py`,
`/api/label-proposals` in `routers/management.py`).

## Data Model

### `channels` — unchanged

`label_id` → `library_labels.id` and `artist_id` → `library_artists.id` already exist (both
`ON DELETE SET NULL`). A confirmed proposal writes one of them; nothing else does.

### `channel_link_proposals` — new

```sql
CREATE TABLE IF NOT EXISTS channel_link_proposals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    channel_id INT NOT NULL,
    kind ENUM('label', 'artist') NOT NULL,
    target_id INT NOT NULL,
    target_name VARCHAR(255) NOT NULL,
    source ENUM('name', 'alias', 'redirect') NOT NULL,
    status ENUM('new', 'confirmed', 'rejected', 'stale') NOT NULL DEFAULT 'new',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decided_at TIMESTAMP NULL,
    decided_by VARCHAR(64) NULL,
    UNIQUE KEY uq_channel_link (channel_id, kind, target_id),
    INDEX idx_channel_link_status (status),
    FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
)
```

- One row per (channel, kind, target), whatever its status. The unique key is what keeps a rejected
  proposal rejected: the next search meets the same triple and the upsert leaves decided rows alone,
  exactly as `rules_label_proposals.RECORD_QUERY` guards on `status = 'new'`.
- `target_id` has no foreign key on purpose: it points into `library_labels` or `library_artists`
  depending on `kind`. A deleted target is caught at confirm time (and by the next search) and turns
  the row `stale`.
- `target_name` is the name as it was proposed, so the list needs no second join per kind and a
  rejected row still says what was rejected.
- `decided_by` mirrors `rules_artists.decided_by` (`curation_rules.actor_name`).

Three edits (AGENTS.md): the `CREATE TABLE` in `services/common/db_init.py` (ordered after
`channels`), `migrate_v41_channel_link_proposals.sql` (the same `CREATE TABLE IF NOT EXISTS`,
re-runnable; recorded by the `schema_migrations` ledger since bug report 068, but correct without
it), and an explicit assertion in `tests/integration/test_schema.py` next to the ledger one
(`EXPECTED_TABLES` itself is derived from the sources since the drift fix).

## Matching

Pure code in `services/music_manager/channel_links.py`, no database access; the router hands it the
rows.

**Key: `text_normalize.unicode_name_key`**, on both sides, for labels as well as artists. Why that
variant:

- It is the artist key (`ArtistNameAnalyzer.normalize`), so "equal" means what artist curation
  already means by the same name. Artist is the larger half of the candidates (708 of ~860).
- Channel names are full of scripts and symbols: Cyrillic, fullwidth (`Ｖａｚｅ`, which NFKD folds
  to `vaze`), `☢ Farfacid ☢`, `ĦȺŦɆɌS`. `ascii_name_key` drops every letter outside ASCII, so two
  different non-Latin names can collapse to the same, shorter key — a false "strong" match — and a
  name of only such letters collapses to the empty string. The Unicode key keeps them.
- Labels have no normalizer of their own (`curation_rules.find_label` is exact equality on
  `library_labels.name`), so there is no established label behaviour to preserve; using the artist
  key keeps one rule for both kinds of candidate.
- `channels.normalized_name` (lowercase, whitespace collapsed) is **not** used for matching: it keeps
  punctuation, so `RSLVD Records †` would not meet `RSLVD Records`. It stays the channel's identity
  key.

A name whose key is empty never matches anything.

**Candidates per kind**

| Kind | Tier | Source rows |
|---|---|---|
| label | `name` | `library_labels` whose name `channels.is_label` accepts (platform names and `__todo`-style placeholders are not labels). |
| artist | `name` | `rules_artists` with `state = 'white'`, joined to `library_artists` on `name` (the link needs a library id). |
| artist | `alias` | `library_artist_aliases.alias` → its `artist_id`, the explicit aliases from the artist edit page. |
| artist | `redirect` | `rules_artists` with `state = 'black'` and a `canonical_name` that is itself white and in `library_artists`: the curator already said this spelling *is* that artist. |

**Rule per (channel, kind)**, applied in `propose_for_channel`:

1. Skip the kind when the channel already has that link.
2. Walk the tiers in order (`name`, then `alias`, then `redirect`); the first tier with any
   candidate decides, later tiers are not consulted — also when the first one ends ambiguous.
3. Distinct targets (by id) in that tier: exactly one → propose it. More than one → keep those whose
   name equals the channel's name after `strip().casefold()`; exactly one left → propose it,
   otherwise the channel is counted as ambiguous for that kind and nothing is proposed.

Telegram channels are not candidates.

## Search (`refresh`)

One call reads everything (five statements: SoundCloud/YouTube channels with their current links,
labels, white artists, aliases, redirects — a few thousand short rows), computes, and writes in one
transaction:

- New triples: `INSERT ... ON DUPLICATE KEY UPDATE target_name = IF(status = 'new', VALUES(target_name), target_name), source = IF(status = 'new', VALUES(source), source)`.
- Open rows (`status = 'new'`) whose triple is not in this run's result → `status = 'stale'`,
  `decided_at = NOW()`. That covers an artist that stopped being white, a renamed or deleted target,
  and a channel linked since.
- Returns `{created, open, withdrawn, ambiguous}`. `created` counts inserted rows (a
  `ROW_COUNT()` of 1 per insert; the upsert leaves existing rows at 0 or 2); a second run in a row
  returns `created = 0, withdrawn = 0`.

Stale rows are not revived: a stale triple that becomes valid again stays stale (the upsert only
touches `new`). Accepted: it takes an explicit reject/confirm history to lose, and the curator can
still link by confirming a fresh proposal once hand-linking exists.

## API Contract

New router `services/music_manager/routers/channel_links.py`, mounted at `/api/channel-links`.
Reads need an API key (`verify_api_key`), writes `rules.manage` — the same split as
`/api/label-proposals`.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/channel-links/proposals` | `status` ∈ `new` (default), `confirmed`, `rejected`, `stale`; optional `kind` ∈ `label`, `artist` | `[{id, channel_id, platform, channel_name, kind, target_id, target_name, source, status, track_count, created_at, decided_at}]`, ordered by `track_count` desc, then channel name | `400` unknown status or kind; `500` no database |
| `POST /api/channel-links/proposals/refresh` | — | `{created, open, withdrawn, ambiguous}` | `500` no database |
| `POST /api/channel-links/proposals/{id}/confirm` | — | `{status: 'confirmed', channel_id, kind, target_id}`, or `{status: 'stale', ...}` when the target no longer exists | `404` unknown id; `409` the proposal was rejected or withdrawn, or the channel is already linked to a *different* target of that kind |
| `POST /api/channel-links/proposals/{id}/reject` | — | `{status: 'rejected'}` | `404` unknown id; `409` already confirmed (unlink instead) |
| `DELETE /api/channel-links/channels/{channel_id}/{kind}` | — | `{status: 'unlinked'}` | `400` unknown kind; `404` unknown channel |

Idempotence: confirming a confirmed proposal returns `confirmed` again without writing; rejecting a
rejected one returns `rejected`. Confirm writes `channels.<kind>_id` and the proposal row in one
transaction, and marks the channel's other open proposals of the same kind `stale`. Unlink sets the
column to `NULL` and turns the confirmed proposal for that channel and kind into `rejected`, so the
next search does not offer it again.

`track_count` is `COUNT(*)` over `library_track_channels` grouped by channel, joined once.

### `GET /api/downloaders/coverage/{source}` — additive

Each account row gains `channel`: `null`, or
`{id, name, label: {id, name} | null, artist: {id, name} | null, open_proposals: int}`.
Not a breaking change: a new key, no existing key changes meaning.

How an account finds its channel: the coverage page is built from the *configured* accounts
(SoundCloud slug `brainimpact`), while a channel is the *folder* the downloader wrote to
(`BRAIN IMPACT`). Neither name can be derived from the other, so the bridge is the archive: the
existing grouped `last_downloads` query also takes `MAX(filename)` (SoundCloud) / `MAX(path)`
(YouTube) per key, `channels.channel_from_path` turns that one sample into `(platform, folder)`,
and `normalize_channel_name` looks it up in one extra statement over `channels` (with its label,
artist and open-proposal count). An account that never wrote a file has no channel. If the folder
changed name over time, the lexically last sample wins; the account then shows one of its channels,
not all.

**Fixed along the way** (bug report 089): the SoundCloud archive files every row under the account's
numeric `soundcloud_id` (157.887 of 157.888 rows), but coverage looked the last download up by
account name, so `last_download_at` was `null` for every SoundCloud account. `configured()` now also
reads `soundcloud_id`, and the archive lookups key on it.

## Cross-App Impact

- `music-manager`: new router and module, coverage row extended.
- `frontend`: `management/ChannelLinkProposals.svelte` as sub-tab `links` in `DownloadersTab.svelte`
  (no new management route, so `router.js`'s `MANAGEMENT_TABS`/`MANAGEMENT_GROUPS` and their mirror
  test are untouched); helpers in `management/channelLinks.js`; the Coverage table gains a
  "Gekoppeld aan" column; i18n keys under `management.downloaders.links.*` and
  `management.downloaders.coverage.colLinked`/`linkProposal`/`unlink`. Existing styleguide
  patterns only (the pill used for the video badge, the table and buttons of Label proposals).
- LMS, MuMa Mobile: none. The app's native management screens are gone (universal UI), and no
  Subsonic endpoint exposes channels.

## Technical Acceptance Criteria

1. `propose_links` proposes a label and an artist for a channel equal to both; nothing for a
   channel that only contains a name; nothing when the key is empty.
2. Several normalised-equal targets: the one whose name equals the channel's case-insensitively
   wins; none or two such → no proposal, counted as ambiguous.
3. The alias tier is consulted only when the name tier has no candidate, the redirect tier only when
   neither has; an ambiguous name tier does not fall through.
4. A channel already linked for a kind gets no proposal of that kind; Telegram channels get none.
5. Only white artists are candidates; a black artist without a white canonical is not.
6. `refresh` twice in a row: the second reports `created = 0, withdrawn = 0` and issues no update to
   decided rows; an open proposal missing from the new result becomes `stale`.
7. Confirm sets `channels.label_id`/`artist_id` and the row to `confirmed` in one transaction and
   stales the channel's other open proposals of that kind; confirming again writes nothing; a
   missing target → `stale`; a channel linked to another target → 409; unknown id → 404.
8. Reject is idempotent; rejecting a confirmed proposal → 409. Unlink clears the column and rejects
   the confirmed proposal.
9. Writes refuse a plain user (403) and admit `rules.manage` and the system key.
10. Coverage: an account whose sample path lies under a known channel carries that channel with its
    links and open-proposal count; one without archive rows carries `null`; SoundCloud
    `last_download_at` is found by `soundcloud_id`.
11. Every new GET and the coverage change run against MariaDB in `tests/integration/test_router_sql.py`;
    `migrate_v41` is re-runnable.
12. Frontend (vitest): the Links tab lists proposals from a mocked response, filters by kind,
    confirms and rejects through the right endpoints, and runs the search showing its counts; the
    coverage table shows a linked label/artist and a "voorstel" marker.

## Hand-linking and the tagger (issue #58)

Implements the two sections of the same name in [functional.md](functional.md).

### Schema: `source` gains `manual`

`channel_link_proposals.source` becomes `ENUM('name', 'alias', 'redirect', 'manual')`. A hand link
is recorded as a row like any confirmed proposal, so the history says who linked what, and unlink
keeps working unchanged (it turns the channel's `confirmed` row of that kind into `rejected`, which
is also what keeps the search from re-proposing it). Three edits: the `CREATE TABLE` in
`db_init.py`, `migrate_v48_channel_link_manual_source.sql` (`ALTER TABLE ... MODIFY source ...`,
re-runnable because a MODIFY to the same definition is a no-op; appending an ENUM value is an
in-place change in MariaDB), and an integration test that stores a `manual` row.

### API — additive

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/channel-links/channels` (API key) | `q` (substring of the name, optional), `limit` 1–50 (default 20) | `[{id, platform, name, track_count, label: {id, name} \| null, artist: {id, name} \| null, open_proposals}]`, SoundCloud/YouTube only, a name equal to `q` first, then one starting with it, then busiest first | `500` no database |
| `GET /api/channel-links/targets` (API key) | `kind` ∈ `label`, `artist`; `q`; `limit` 1–50 (default 20) | `[{id, name}]`. Labels: `library_labels` that `channels.is_label` accepts. Artists: `rules_artists.state = 'white'` joined to `library_artists` by name, the same set the proposals use. Blank `q` → `[]`. Same ordering rule. | `400` unknown kind |
| `PUT /api/channel-links/channels/{channel_id}/{kind}` (`rules.manage`) | `{target_id: int}` | `{status: 'linked', channel_id, kind, target_id, target_name, queued}` | `400` unknown kind; `404` unknown channel or target; `409` channel linked to a different target of that kind, artist not approved, or label is a placeholder |

`PUT` is idempotent: the same link again returns `linked` without writing and without queueing.
Otherwise, in one transaction: `channels.<kind>_id` is set; the triple is upserted as
`status = 'confirmed', source = IF(row existed, source, 'manual')` with `decided_at`/`decided_by`
(so an open or rejected proposal for exactly that link becomes the confirmed one, and a new row is
`manual`); the channel's other open proposals of that kind turn `stale`, as in confirm.

`confirm` and `unlink` gain `queued` in their response (additive).

The `LIKE` pattern escapes `%`, `_` and `\` — a channel called `100%` must not match every name.

### Tagger

- **`ChannelLinkHelper`** (`services/common/Helpers/ChannelLinkHelper.py`, registry key
  `channelLinkHelper` in `Cache.databaseHelpers`). One statement loads every linked channel:
  `(platform, normalized_name) → (label name, artist name)`, where the artist half is only filled
  when that artist is still `white` in `rules_artists`. `link_for(path)` runs
  `channels.channel_from_path` + `normalize_channel_name` — the same two functions the scanner files
  a track under a channel with, so the tagger and `library_track_channels` cannot disagree about
  which channel a file belongs to. It has `reload()` (called by `Tagger.run` before each round and
  by the router after every link change) and the same 60-second expiry as `LookupTableHelper`, so
  the downloader and importer processes catch up on their own. `set_links(rows)` for tests; the
  `mock_base` Cache stub holds a real, empty one.
- **`ApplyChannelLinkRule`** (`services/tagger/Song/rules/`), in the SoundCloud (and so Telegram)
  and YouTube stacks directly after `InferArtistFromTitleRule`: after the title has had its say,
  before remixer/feature extraction appends to the artist, and before every genre and artist
  curation rule, so those see the linked values.
  - Label: `PUBLISHER` is replaced when `channels.is_label(current)` is false (empty, a platform,
    a placeholder). For these song types that is every time, since `parse()` writes the platform.
  - Artist: each `ARTIST` value whose `unicode_name_key` equals the key of one of the song's
    `channel_stand_ins()` is replaced by the linked name; duplicates are dropped, order kept. No
    `ARTIST` at all → the linked name. `BaseSong.channel_stand_ins()` returns `[]`; SoundCloud
    returns the channel folder and the uploader, YouTube the folder and the channel name it built
    the album from. `ALBUM_ARTIST` is not touched: on YouTube it is the key
    `InferGenreFromAlbumArtistRule` looks the channel up by.
- **`InferGenreFromLabelRule`** joins both stacks right after `InferGenreFromArtistRule` (the same
  place it has in the label stack), so the linked label's `rules_label_genre` rows apply. It reads
  `PUBLISHER`, which without a link is the platform and matches no rule (checked on production).
- `CheckArtistRule` still runs later, so a correction or rejection recorded for the linked name
  applies to it like to any other.

### Scanner: a platform file may carry exactly one label

`ScannerManager._resolve_label_id` refused every label for a file under a platform folder
(`path_can_carry_a_label`), which is right for the platform name itself but would also throw away
the label the tagger now writes. The refusal stays, with one exception: when the file's channel
(`channel_from_path` + `normalize_channel_name`, one extra `SELECT` joining `channels` to
`library_labels`) is linked to a label and the file's publisher is that label's name (case
insensitive), that label id is used. Any other publisher on a platform file is still refused —
including a stale one left behind after an unlink, until the retag rewrites it. The label row
already exists (the link points at it), so nothing is inserted.

### Queueing the retag

`RescanInvalidator.invalidate_by_channel(channel_id, reason)` marks every
`library_media_files.file_path` whose track is in `library_track_channels` for that channel. The
router calls it after the transaction commits, for `confirm`, `PUT` and `unlink` (not for an
idempotent repeat), with reason `channel_link`, and never lets it fail the request (the link is
committed; the daily walk repairs a missed queue). `channel_link` is added to
`ProcessedFilesHelper.BULK_REASONS`: it is served after decisions and after new files, because one
confirm can queue 5.154 files and would otherwise sit in front of a genre decision.

### Cross-app impact

- `music-manager`: three endpoints, two responses extended, helper, rule, stack order.
- `frontend`: `management/ChannelLinkByHand.svelte` at the top of the Links tab; the
  Coverage table's "Gekoppeld aan" column gains a **Koppelen** button for a channel with no link
  and no open proposal, which opens the tab with that channel preselected (`DownloadersTab` passes
  it through). The pickers reuse the suggestion list of `MultiPicker.svelte`, as a single-value
  variant (recorded in `docs/styleguide.md`).
- LMS, MuMa Mobile: none directly. LMS shows the label once it rescans the retagged files; the app
  gets it through LMS.

### Acceptance criteria (hand-link and tagger)

13. `PUT` links a channel, upserts a `manual` confirmed row, stales rival open proposals, queues the
    channel's files; repeating it writes and queues nothing; a different existing link, an
    unapproved artist and a placeholder label are 409; unknown channel/target 404; a plain user 403.
14. `GET /channels` and `GET /targets` run against MariaDB (integration), escape `LIKE` wildcards,
    offer only white artists and real labels.
15. `ApplyChannelLinkRule`: label replaces a platform publisher, never a real label; an artist
    stand-in (any spelling that keys equal) is replaced, a title-supplied artist is not; an empty
    artist is filled; an unlinked channel changes nothing.
16. The SoundCloud and YouTube stacks contain `ApplyChannelLinkRule` directly after
    `InferArtistFromTitleRule` and `InferGenreFromLabelRule` after `InferGenreFromArtistRule`
    (`RuleStackTest`), and a SoundCloud song parsed end-to-end through its real stack comes out with
    the linked label and artist (so the rule is wired, not only tested).
17. `channel_link` is a bulk reason; `invalidate_by_channel` selects by channel.
18. Frontend: the hand-link panel searches channels and targets through the right endpoints, links
    with `PUT` and reports the queued count, shows the 409 message; the coverage table's Koppelen
    button opens the tab with the channel picked.

## A label page's channels (issue #122)

Implements the section of the same name in [functional.md](functional.md).

### API — additive

`GET /api/channel-links/by-label?name=<label>` (API key, like the other reads). Keyed on the name,
because that is what the label page's route (`/label/<name>`) carries; `library_labels.name` is
unique. Response `[{id, platform, name, track_count, artist: {id, name} | null, album, source_url}]`,
busiest first. An unknown label, a label without channels and a blank name are all `[]`, not `404`:
every label page asks, and almost none has a channel.

Cost: one statement over indexes -- `library_labels.name` (unique) -> `channels.label_id`
(`idx_channel_label`) -> a correlated `COUNT(*)` per channel on `library_track_channels.channel_id`
(`idx_track_channel_channel`) -- plus, only when there are channels, one `SELECT name` per platform
present from the followed-account tables (a few hundred short rows each). No new index, no schema
change, no migration.

- `album` = `channel_links.channel_album(platform, name)`: `<publisher> (<channel>)` with the
  publisher the tagger writes (`Soundcloud`, `Youtube`, `Telegram`), which is the album
  `SoundcloudSong`/`YoutubeSong` give every download of the channel.
- `source_url` = `channel_links.source_url(...)`: the followed account whose `account_key` (letters
  and digits, casefolded, so `@traxtormrecords` meets `Traxtorm Records`) equals the channel's, when
  exactly one does; SoundCloud `https://soundcloud.com/<slug>`, YouTube `https://www.youtube.com/@handle`
  or `/channel/<id>` (the same rule as the coverage table). The exact bridge (the archive path, as
  the coverage page uses) would mean scanning `downloads_soundcloud_archive.filename`, an unindexed
  `TEXT` column of ~158.000 rows, on every label page; the name match costs nothing and on production
  finds an account for roughly 40 % of SoundCloud and half of the YouTube channels. A failure to read
  the account tables costs the link, never the list.

### Frontend

- `src/lib/labelChannels.js`: `fetchLabelChannels` (session cache per label name),
  `channelAlbumView` (Subsonic `search3`, albums only, exact case-insensitive name match -> `album:<id>`),
  `channelDestination` (album view, else `source_url` through `platform.system.openUrl`, else
  `search:<name>`). The album is resolved on tap, not on load: resolving every card up front would put
  one `search3` per channel through the LMS proxy queue on every label page.
- `src/lib/LabelChannels.svelte`, rendered by `Dashboard.svelte` between the label header and its
  track list. `SectionState` for skeleton/error/retry; skeletons only for `rules.manage` (see the
  functional table). **Manage links** sets `downloaderSubTabRequest` (new, unpersisted store)
  to `links`, `activeManagementTab` to `downloaders` and opens `management`; `DownloadersTab` takes the
  request once on mount. No new route: the Links sub-tab has no URL of its own.
- i18n: `labelChannels.title|manage|none` (nl, en; the dialects fall back).

### Cross-app impact

- `music-manager`: one read endpoint, two pure helpers. `frontend`: one section, one store, one prop-less
  change to `DownloadersTab`. MuMa Mobile shows the web interface, so it gets the section with no
  native change. LMS: none.

### Acceptance criteria (label page)

19. `by-label` returns a label's channels busiest first with counts, `album` and `source_url`, runs
    against MariaDB (`test_router_sql.py`), reads the account tables only for the platforms present,
    survives an unreadable account table, and returns `[]` for a blank or unknown name.
20. `source_url` is set only for exactly one matching account; `channel_album` follows the tagger's
    publisher names.
21. Frontend (vitest): the section lists cards from a mocked answer, opens the album or the source
    page, hides for a listener with no channels, shows a curator the skeleton, empty line and the
    Links link, retries after an error, and shows the cached answer on a revisit;
    `DownloadersTab` starts on a requested sub-tab once. Playwright: the section at phone, tablet and
    desktop widths without widening the page, and the curator's link landing on Links.

## Related Docs

- [channel-coverage/technical.md](../channel-coverage/technical.md) — the coverage endpoint.
- [artist-curation/technical.md](../artist-curation/technical.md) — white/black/canonical.
- `services/common/text_normalize.py` — the name key variants.
- `docs/bug-reports/089-soundcloud-coverage-last-download-never-found.md`.
