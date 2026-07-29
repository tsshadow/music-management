# Artists Page Shows No Images

# status: fixed

# reported problem
`https://music.example.com/artists` toont geen afbeeldingen voor artiesten — the Spotify-style
player's Artists grid (and the Artist detail view) render a broken-image icon for essentially every
artist, even though `docs/bug-reports/004-artist-images-not-working.md` and
`docs/bug-reports/006-artist-images-tab-zero-stats.md` already fixed the manager tab and the LMS DB
sync path.

# Possible reason
`getArtistImageUrl()` (`services/music-management-server/src/lms/ui/spotify-ui/src/lib/utils.js`)
only has two cases: use the artist's native LMS `coverArt` if the scanner has associated one, or else
fall back to `/media/artist-images/{id}/primary.jpg`. That fallback path is never reachable from
`music.example.com`: `/media/artist-images` is only mounted as a `StaticFiles` route on
`music_manager` itself (`services/music_manager/main.py:78`). The public LMS server only registers
resources at `/rest`, `/muma`, `/legacy` and `/` (the SPA static/catch-all, `SpotifyResource` in
`services/music-management-server/src/lms/main.cpp`) — nothing forwards `/media/artist-images/*`
requests to `music_manager`. Every such `<img>` request therefore falls through to the SPA's
catch-all and gets back `index.html`, which the browser renders as a broken image.

This is distinct from bug 004's second finding (the LMS↔MuMa DB sync path that populates
`preferred_artwork_id`/native `coverArt`): even with that path fully working, an artist without a
*native* LMS artwork association (the common case, since MuMa's own cached images are the primary
image source) always falls into this broken fallback branch.

The correct, already-authenticated path for this exists: `MumaResource.cpp` proxies
`/muma/api/artists/{name}/image` through to MuMa's real `/api/artists/{name}/image` endpoint (this is
exactly what `ArtistImagesTab.svelte`'s manager-tab fix in bug 004 uses), keyed by artist *name*, not
ID.

# solution
`getArtistImageUrl()` now falls back to `` `/muma/api/artists/${encodeURIComponent(artist.name)}/image?${authParams}` ``
instead of the unreachable `/media/artist-images/{id}/primary.jpg` path, reusing the same Subsonic
`authParams` (`u`/`p`) already used for the `coverArt` branch just above it, consistent with how every
other authenticated image/proxy request in this UI is built.
