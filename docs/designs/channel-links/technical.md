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
`channels`), `migrate_v40_channel_link_proposals.sql` (the same `CREATE TABLE IF NOT EXISTS`,
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

**Fixed along the way** (bug report 087): the SoundCloud archive files every row under the account's
numeric `soundcloud_id` (157.887 of 157.888 rows), but coverage looked the last download up by
account name, so `last_download_at` was `null` for every SoundCloud account. `configured()` now also
reads `soundcloud_id`, and the archive lookups key on it.

## Cross-App Impact

- `music-manager`: new router and module, coverage row extended.
- `frontend`: `management/ChannelLinkProposals.svelte` as sub-tab `links` in `DownloadersTab.svelte`
  (no new management route, so `router.js`'s `MANAGEMENT_TABS`/`MANAGEMENT_GROUPS` and their mirror
  test are untouched); helpers in `management/channelLinks.js`; the Volledigheid table gains a
  "Gekoppeld aan" column; i18n keys under `management.downloaders.links.*` and
  `management.downloaders.coverage.colLinked`/`linkProposal`/`unlink`. Existing styleguide
  patterns only (the pill used for the video badge, the table and buttons of Labelvoorstellen).
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
    `migrate_v40` is re-runnable.
12. Frontend (vitest): the Koppelingen tab lists proposals from a mocked response, filters by kind,
    confirms and rejects through the right endpoints, and runs the search showing its counts; the
    coverage table shows a linked label/artist and a "voorstel" marker.

## Related Docs

- [channel-coverage/technical.md](../channel-coverage/technical.md) — the coverage endpoint.
- [artist-curation/technical.md](../artist-curation/technical.md) — white/black/canonical.
- `services/common/text_normalize.py` — the name key variants.
- `docs/bug-reports/087-soundcloud-coverage-last-download-never-found.md`.
