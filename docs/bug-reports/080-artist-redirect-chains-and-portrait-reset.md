# Artist Redirect Chains Survive Reject/Undo; A Cleared Portrait Stays Visible

# status: fixed

# reported problem
Two audit items from 2026-09-23 (`onderzoeksrapport-muma-2026-09-23.md`).

**B15, artist-curation redirect chains.** `routers/artist_curation.py` records a rewrite as
`rules_artists(name, state='black', canonical_name)` and mirrors it into
`rules_ignored_artists(name, corrected_name)`, the table the tagger reads. Rejecting or undoing a
name X changed only X's own rows. Every `Y -> X` stayed, so:

- rejecting X with a correction Z left `Y -> X -> Z`. The tagger looks up one hop, so it wrote the
  rejected X, and only a second retag reached Z;
- rejecting X outright left `Y -> X`, and X is dropped: a credit that should have been a name
  became a rewrite to a rejected name;
- undoing X left `Y -> X` pointing at a name nobody had approved any more;
- nothing reported any of this, and the Tagger tab (`POST /api/rules/artist-redirects`) could still
  point a name at a rejected artist or close a loop (`A -> B`, `B -> A`).

The Last.fm half of B15 (the grey-star placeholder counted as a +100 candidate) was already fixed:
`LASTFM_PLACEHOLDER_HASH` in `artist_image_fetcher/providers/lastfm.py` skips it, covered by
`test_the_generic_placeholder_image_is_never_a_candidate`.

**A3.8 remainder, "clearing a portrait is undone on the next start".** The core of it was fixed in
!931 (0.72.2): a clear now sets `image_status = 'cleared'`, which the start-up bulk run and a plain
single-artist fetch skip. What was left: the portrait stayed *visible* after a clear.

# Possible reason
**B15.** `decide()` and `undo()` only ever wrote the rows of the names they were given. The check
"a correction may not point at a rejected name" existed only for a new correction, not for the
redirects already pointing at a name that was then rejected. `FilterTableHelper` answered one hop.

**A3.8.** A clear only changed `library_artists`. Two copies outside that table kept the picture:

- `sync_artist_images_to_server` (start-up and hourly) only ever *sets* the server's
  `artist.preferred_artwork_id`. A cleared artist is no longer selected by it, so the server kept
  the artwork, and the web player -- which asks the server first (`getArtistImageUrl`,
  `coverArt`) -- kept showing the removed portrait, restart after restart;
- the published `primary.jpg`/`thumb_<size>.jpg` in the artist's image directory, behind the fixed
  URL `/media/artist-images/{id}/primary.jpg`, were never removed. Selecting another stored image did
  not rewrite them either, so that URL showed the previous portrait.

# solution
**B15.**
- Before a name is rejected or undone, the redirects pointing at it are settled in the same
  transaction (`_release_redirects_to`, both tables, case-insensitive). Decided, and documented in
  the docstring and `docs/designs/artist-curation/technical.md`:
  - rejected **with** a correction Z: every `Y -> X` becomes `Y -> Z` (the curator said Y is X and X
    is Z; nothing is lost, no chain is left);
  - rejected **without** one, or undone: every `Y -> X` is forgotten and Y goes back to the queue.
    The premise of the redirect is gone and what Y is instead is not something to guess; turning Y
    into a plain rejection would strip the credit from every file on the next retag.
  The reply lists both (`repointed`, `returned_to_queue`). `decide` and `undo` now run in one
  transaction (the pool is autocommit), and `undo` of a name without a decision changes nothing.
- A redirect to a rejected name stays refused on the curation page and is now refused on the
  Tagger tab as well, together with a redirect that would close a loop.
- `FilterTableHelper(..., follow_chains=True)` -- used for `rules_ignored_artists` in `Cache` and
  the three tagger rules -- resolves every correction to the end of its chain on preload
  (`resolve_redirect_chains`), with a depth bound and a cycle guard: a looping key keeps its one-hop
  answer, as before.
- `GET /api/rules/artists/redirects/issues`: read-only report of dangling redirects (final target
  rejected, dropped, or -- for a page decision -- without a decision), loops, and multi-hop chains.
  Rows seeded by `migrate_v26` (`legacy-redirect`) never had an approved target, so "no decision"
  is not reported for them.

**A3.8.**
- The clear removes `primary.jpg` and `thumb_<size>.jpg` (the stored images stay selectable);
  selecting a stored image republishes them from it (`ImageStorage.unpublish_primary` /
  `publish_primary`). A file-system failure is logged and does not fail the committed change.
- The server sync ends with `_unset_cleared_artwork_on_server`: for a `cleared` artist it sets
  `preferred_artwork_id = NULL` when the server's artwork is one of that artist's stored files.
  Artwork the server found on its own is left alone.

Other A3.8 parts, verified: the Spotify token is renewed before `expires_in` runs out and once more
on a 401 (bug 043, `providers/spotify.py` `_get_token`/`_request`); a portrait that was found but
could not be downloaded or saved no longer marks the artist `failed` for 30 days
(`fetcher.py` `_record_download_failure`, status unchanged, counted in the run summary).

Tests: `FilterTableHelperTest` (chains, casing, loops, depth), `test_artist_curation.py`
(re-point, requeue, undo, atomicity, report), `test_management_router.py` (Tagger tab refusals),
`test_storage.py` and `test_artist_images_router.py` (published copies, server artwork), and
`tests/integration/test_router_sql.py` (`ArtistRedirectsTest`, the cleared-artwork query, the new
read endpoint).
