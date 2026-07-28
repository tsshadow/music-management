# Artist Images Tab Always Shows 0 / 0 Artists

# status: fixed

# reported problem
The "Artist Images" manager tab always shows "Bibliotheek Status: 0 / 0 artiesten", the search box
never returns any results, and the "RESCAN" button's progress never updates, even though the
underlying database is correctly populated (production: 51,315 artists total, 11,762 with an image).

# Possible reason
The LMS reverse-proxy (`MumaResource.cpp`) has a dedicated block that intercepts every request path
starting with `/api/artists/` *before* the generic `/api/*` MuMa pass-through proxy ever gets a
chance to run. That block only correctly implements two specific shapes:
1. A path ending in `/image` (artist image proxy).
2. A path that is a single, plain artist-ID segment with no further `/` (used by the player's own
   Artist detail view, `ArtistView.svelte`, for a native genre lookup, e.g. `/api/artists/123`).

Every other `/api/artists/*` request used by the manager UI — `/api/artists/images/stats`,
`/api/artists/search`, `/api/artists/search-all`, `/api/artists/fetch-progress`, and
`POST /api/artists/{id}/fetch-image` — fell into the `else` branch, which tries to parse everything
after `/api/artists/` as a numeric ID. For all of those it fails and the request is rejected with
`400 Invalid artist ID` before it ever reaches `music-manager`. This has nothing to do with the data
in the database (which was verified as correct); it is a pure request-routing bug in the reverse
proxy, reproduced directly against production:
```
curl -H "X-API-Key: <key>" https://music.example.com/muma/api/artists/images/stats
# -> HTTP 400, body: "Invalid artist ID"
```

# solution
Narrowed the `/api/artists/` interception in `MumaResource.cpp` to only trigger for the two shapes
it actually implements (image request, or a single plain ID segment with no further `/`). Any other
`/api/artists/*` path now falls straight through to the existing generic `/api/*` MuMa proxy further
down in the same handler, exactly like every other `music-manager` REST endpoint.
