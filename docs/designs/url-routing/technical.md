# URL Routing — Technical Design

Implements [`functional.md`](functional.md).

## Data Model

None. Routing is derived entirely from the existing stores; nothing is persisted server-side and no table
changes.

The stores involved are all pre-existing:

| Store | Role in routing |
|---|---|
| `activeView` | The screen. Detail screens encode their argument as `"kind:argument"` (`artist:123`, `genre:Hardcore`). |
| `currentPlaylist` | Supplies the id for `playlist-detail`, which `activeView` cannot carry. |
| `activeSettingsTab` | The tab inside Settings. |
| `activeManagementTab` | The tab inside Management. |
| `credentials` / `mumaSessionActive` | Whether there is a session; without one every address resolves to `/login`. |

`activeSettingsTab` and `activeManagementTab` remain persisted in `localStorage`. The URL wins when it
names a tab; the stored value is the fallback when it does not.

## API Contract

No HTTP API changes. The one server-side change is how LMS's static handler decides between serving a file
and serving the SPA shell:

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /<any frontend route>` | Any path with no extension, or with an extension outside the static-asset set | `index.html` (200) | — |
| `GET /assets/<file>.<ext>` | An extension in the static-asset set (`.css .ico .jpeg .jpg .js .json .map .mjs .png .svg .ttf .webmanifest .webp .woff .woff2`) | The file (200) | 404 when the file does not exist |
| `GET /../<path>` | Any path escaping the docroot after normalization | — | 404 |

Not a breaking change: every address that resolved before still resolves the same way. The set of addresses
that return `index.html` only grows, and it grows to include exactly the routes that previously 404'd.

## Cross-App Impact

- **frontend** — the routing table, the App shell that drives it, and the two tab-owning screens.
- **music-management-server (LMS)** — the SPA fallback in `SpotifyResource::handleRequest`.

These ship together: the frontend can produce addresses containing a dot (a genre named `nu.jazz`), and
without the LMS change those addresses 404 on refresh.

MuMa Mobile is unaffected — it does not use the web UI's routes. The nginx reverse proxy is unaffected: it
already forwards everything that is not `/rest` or `/muma` to the same handler.

### Structure

`services/frontend/src/lib/router.js` holds the whole routing table as two pure functions:

- `viewToPath({ view, loggedIn, playlistId, settingsTab, managementTab })` → path, or `null` when the view
  has no address and the URL should be left alone.
- `pathToState(path)` → `{ view, playlistId?, settingsTab?, managementTab? }`, always with a `view`.

`App.svelte` keeps only the glue: read the path on mount, listen for `popstate`, and push a new history
entry from an `$effect` whenever the computed path differs from the current one. Keeping the table pure is
what lets it be tested without mounting the app.

`SETTINGS_TABS` and `MANAGEMENT_TABS` are exported from the same module and are the single source of truth
for which tabs exist. `Settings.svelte` and `Management.svelte` both use them to fall back to their first
tab when the active one is unknown.

### Routing table

| View state | Path |
|---|---|
| `home` | `/` |
| `login`, or no session | `/login` |
| `songs`, `sets`, `albums`, `genres`, `labels`, `artists`, `playlists`, `memories`, `history`, `starred` | `/<view>` |
| `genre:<name>`, `label:<name>`, `search:<query>` | `/genre/<encoded>`, `/label/<encoded>`, `/search/<encoded>` |
| `artist:<id>`, `album:<id>` | `/artist/<id>`, `/album/<id>` |
| `playlist-detail` + `currentPlaylist.id` | `/playlist/<id>` |
| `settings` (+ tab) | `/settings` or `/settings/<tab>` |
| `management` (+ tab) | `/management` or `/management/<tab>` |
| anything else | no path; the URL is left as it is |

Genre, label and search arguments are free text — they contain colons, slashes and ampersands — so they are
taken whole and percent-encoded. Artist and album arguments are opaque server ids and are left as they are,
so links created before this change keep working. A trailing slash is ignored. An unrecognised path
resolves to `home` rather than erroring, because the URL is user input.

`playlist-detail` with no id yet returns `null` instead of `/playlist`: the view is set before the fetch
that fills in the playlist, and writing a bare `/playlist` in that window would break a refresh.

### SPA fallback

`SpotifyResource::handleRequest` previously fell back to `index.html` only when the requested path had no
extension (or ended in `.html`). Any other dot made it a 404 — so `/genre/nu.jazz` and `/search/1.21 gigawatts`
failed on refresh. The test is now an explicit list of the extensions the built frontend actually ships;
anything else is treated as an application route.

The same function now also rejects paths that escape the docroot. The path comes from the URL, and
`/../lms.conf` previously resolved to a real file outside the docroot and was served verbatim. The path is
normalized with `lexically_normal()` and must still start with the docroot, or the request 404s.

## Technical Acceptance Criteria

1. `viewToPath` and `pathToState` round-trip every address in the routing table: `viewToPath(pathToState(p))
   === p`.
2. A genre or label containing `&` and `/` survives the round trip unchanged.
3. `viewToPath` returns `null` for `playlist-detail` without an id, and the URL is therefore not rewritten.
4. `pathToState('/settings')` returns no `settingsTab`, and `App` consequently leaves the stored tab alone.
5. `pathToState('/settings/scan-settings')` and `pathToState('/management/nope')` drop the unknown tab
   rather than passing it on.
6. Mounting `App` at `/management/scanner` opens the scanner tab; at `/settings/about`, the about tab.
7. Setting `activeView` to `history`, or opening a playlist, writes the matching path into the address bar.
8. `Management.svelte` resets an unknown `activeManagementTab` to `overview`, as `Settings.svelte` already
   did for its own tabs.
9. Every tab button the Management sidebar renders for an administrator maps to an entry in
   `MANAGEMENT_TABS`, so a tab added to the sidebar alone cannot silently lose its address.
10. The LMS fallback returns `index.html` for `/genre/nu.jazz` and `/management/scanner`, returns 404 for a
    missing `/assets/app.js`, and returns 404 for `/../lms.conf`.

## Related Docs

- [docs/styleguide.md](../../styleguide.md)
- [services/music-management-server/nginx/reverse-proxy.conf](../../../services/music-management-server/nginx/reverse-proxy.conf) — why `/rest` and `/muma` bypass this handler
