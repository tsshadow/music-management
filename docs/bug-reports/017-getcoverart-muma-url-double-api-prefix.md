# title: Artist images (and other native `coverArt` images) render black — `/rest/getCoverArt` 502s for MuMa-backed artwork

# status: fixed

# reported problem
`user`: images zijn zwart voor artiesten. Op disk bestaat `/mnt/music/artists/<id>/` prima (ook
zichtbaar vanuit de `music-manager` container). Het rechtstreeks opvragen van een specifieke
artiestenfoto werkt (`https://music.example.com/muma/api/artists/AVI8/image?...` geeft netjes
een JPEG terug), maar de grote profielfoto op de artiestenpagina (`ArtistView.svelte`) en de
afbeeldingen op de Beheer → Artists-pagina laten allebei een zwart vlak zien.

# Possible reason
`getArtistImageUrl()` (`services/frontend/src/lib/utils.js`, the file actually built into
`music.example.com`'s docroot per `Dockerfile-release`'s `svelte-build` stage — see
`docs/bug-reports/014-artists-page-no-images.md`) prefers the artist's *native* Subsonic `coverArt`
field over the MuMa image proxy, when present:
```js
if (artist && artist.coverArt) {
  return `/rest/getCoverArt?id=${artist.coverArt}&size=300&${authParams}`;
}
```
For an artist whose artwork only exists via MuMa's own cache (the common case, confirmed by bug
004: only ~11.7k of ~51k artists have any cached image at all), LMS's own Subsonic layer
(`CoverArtId.cpp`) synthesizes a special `coverArt` id shaped `muma-<hex-encoded-artist-name>-0`
(confirmed live: `search3` for "AVI8" returns `"coverArt": "muma-41564938-0"`, where `41564938` is
"AVI8" hex-encoded). `/rest/getCoverArt` (`MediaRetrieval.cpp`'s `handleGetCoverArt`) recognizes
this `muma-...` id shape and proxies the request to MuMa's `/api/artists/{name}/image` — mirroring
the *already-working* proxy in `MumaResource.cpp` (used for the direct `/muma/api/artists/...`
URL, which the reported test URL exercises and which is not affected by this bug).

Reproduced live:
```
curl ".../rest/getCoverArt.view?id=muma-41564938-0&size=300&u=...&p=..." 
# -> HTTP 502, body: "MuMa returned error: 502"
```
while the *identical* underlying MuMa call, made via `MumaResource.cpp`'s proxy
(`/muma/api/artists/AVI8/image`), returns a real `200` JPEG every time.

**Root cause**: both proxies build their outgoing MuMa request as `<mumaApiUrl> + "/api/artists/" +
name + "/image"`, so `mumaApiUrl` must have any existing `/api` suffix stripped first (the primary
config key, `music-management-url`, is documented/used *with* a `/api` suffix — see
`.env.example`: `MUSIC_MANAGEMENT_URL=http://music-management.example.com/api` — and other call
sites, e.g. `MusicManagementPasswordService.cpp`/`UserSynchronizer.cpp`, rely on exactly that and
append their own sub-paths directly, no stripping needed there since those sub-paths don't
themselves start with `/api`). `MumaResource.cpp`'s constructor correctly strips a `/api` suffix
from *either* config key it might have resolved. `MediaRetrieval.cpp`'s `handleGetCoverArt` only
applied that same stripping to the `music-management-api-url` *fallback* value, not to the primary
`music-management-url` value — so whenever the latter was configured (the normal case), the
resulting base URL kept its `/api` suffix, and the actual outgoing request became
`.../api` + `/api/artists/.../image` = `.../api/api/artists/.../image`, a double-prefixed URL that
fails at the connection/URL-construction level in the underlying HTTP client (surfaced as a `502`
from the proxy's own `onFailureFunc`, not as a `404` from MuMa itself — MuMa was never actually
reached).

This affects every place the *player* UI resolves an artist's `coverArt` through the native
Subsonic path when it's a MuMa-synthesized id — not just the big profile photo on
`ArtistView.svelte`, but also similar-artist tiles on the same page, and any other component using
`getArtistImageUrl()`/raw `coverArt` for an artist without native LMS artwork. It does **not**
affect the Beheer → Artists tab (`ArtistImagesTab.svelte`), which calls the MuMa image proxy
directly (`${API_BASE}/api/artists/{name}/image`, i.e. `MumaResource.cpp`'s already-correct path)
rather than going through `/rest/getCoverArt` — any black images remaining there after this fix are
a separate issue (most likely artists that genuinely have no cached image yet, per the ~77%-missing
stat in bug 004) and need to be re-checked independently once this fix is live.

# solution
`MediaRetrieval.cpp`'s `handleGetCoverArt`: apply the same `/api`-suffix-stripping to
`music-management-url` that `MumaResource.cpp`'s constructor already does, regardless of whether
the value came from `music-management-url` or the `music-management-api-url` fallback, before using
it as the MuMa HTTP client's base URL.
