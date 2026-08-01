# Artist Images Tab Shows No Artists When Searching

# status: fixed

# reported problem
The manager's Artist Images tab (`/management`, tab "images") shows no artists at all when you
search for one. The reporter also asked for the tab to become a real image *manager*: minimally,
search an artist and see its image.

# Possible reason
The backend and the LMS proxy in front of it were verified healthy against production while
investigating: `GET /muma/api/artists/search?q=daft` returns Daft Punk and Daft Monk in ~25ms, and
`GET /muma/api/artists/Daft%20Punk/image` returns a 50 KB `image/jpeg`. The failure was therefore in
the tab itself, which had several ways to render a completely blank page with no explanation:

1. **Any non-200 response rendered as "nothing".** `searchArtistImages()` assigned
   `await res.json()` straight into `artistsWithImages` / `allArtists` without checking `res.ok`.
   FastAPI's error bodies are objects (`{"detail": ...}`), so on a 401/403/500 the list state became
   an object whose `.length` is `undefined`. That made `{#if artistsWithImages.length > 0}` false
   *and* the `artistsWithImages.length === 0 && allArtists.length === 0` empty-state false, so the
   page rendered neither results nor a message. A thrown `res.json()` (proxy 502, network error)
   was swallowed by `catch { console.error }` and left the previous list on screen.
2. **The query was never URL-encoded.** `?q=${artistImageSearch}` interpolated raw user input, so
   an artist name containing `&` truncated the query and one containing `#` dropped it entirely.
3. **Two endpoints, two half-lists.** `/search` only returns artists that already *have* an image
   (it `JOIN`s `library_artist_images`) and `/search-all` returns artists with no image metadata at
   all. The tab stitched them together and filtered the second list against the first, so which
   artists appeared depended on which of the two calls happened to succeed.
4. **Every keystroke fired two uncoordinated requests**, so a slower earlier response could
   overwrite a newer one — as could the `q=''` search that the progress poller fires on mount.

# solution
A new backend endpoint plus a rewritten tab.

`GET /api/artists/manage/search?q=&only=all|with|without&limit=&offset=` returns *every* matching
artist with its primary-image metadata `LEFT JOIN`ed on, as `{items, total, limit, offset}`. One
call, one complete list, so the manager no longer has to reconcile two partial ones.

Manual image management (all POST-only on sub-paths of `/image`, because LMS's `MumaResource`
intercepts any path ending in exactly `/image` and forwards `DELETE` as `POST`):

- `POST /api/artists/{id}/image/url` — download an image from an http(s) URL and make it primary
- `POST /api/artists/{id}/image/upload` — store a base64/data-URL encoded upload (the proxy forwards
  request bodies as text, so binary multipart would be corrupted in transit)
- `POST /api/artists/{id}/image/clear` — unset the primary image, keeping stored images re-selectable
- `POST /api/artists/{id}/image/select/{image_id}` — promote a stored image to primary
- `GET /api/artists/{id}/images` — list everything stored for one artist

`ArtistImagesTab.svelte` now owns its own state and fetching (the pattern `LibraryTab`/
`AdvancedLibraryTab` already use) instead of receiving five props from `Management.svelte`. It
checks `res.ok`, shows the backend's `detail` in an error banner with a retry button, guards every
list with `Array.isArray`, builds the query with `URLSearchParams`, debounces input by 250ms, and
pages results with a "Meer laden" button. Per artist it offers auto-fetch, upload, set-from-URL,
clear, and a detail dialog listing the stored images so another one can be made primary.

The old `/search` and `/search-all` endpoints are left in place; nothing in the UI calls them
anymore.

# tests
- `services/music_manager/tests/test_artist_images.py` — 12 tests over the new endpoints, including
  that `manage/search` returns artists *without* an image, that `only=` reaches the SQL, that
  `select` refuses an image belonging to another artist, and that upload rejects invalid base64.
- `services/frontend/tests/unit/artistImagesTab.test.js` — 8 component tests, including that a
  found artist's image is rendered, that a failing search shows an error instead of a blank page,
  and that the query is URL-encoded.
- `services/frontend/vite.config.js` — resolves Svelte's browser build under Vitest so component
  tests can mount at all (previously `mount(...) is not available on the server`).
