# Favorite Genres — Technical Design

> Implements the already-agreed [`functional.md`](functional.md).

## Data Model

No new table or migration. Reuses the existing generic `user_app_settings` table
(`services/music_manager/routers/users.py`, `init_db`):

```sql
CREATE TABLE IF NOT EXISTS user_app_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    app_id VARCHAR(50) NOT NULL,
    settings_json LONGTEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY (user_id, app_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
)
```

This is the same table/pattern Ultrasonic used for its own settings backup under
`app_id = 'ultrasonic'` (that screen has since been removed; the endpoints stayed). The web frontend uses a new, dedicated
`app_id = 'frontend'` row per user. `settings_json` is an opaque JSON-encoded string owned by the
frontend; today it holds a single key:

```json
{ "favoriteGenres": ["Techno", "House"] }
```

Kept as an object (not just an array) so future frontend-only settings can be added under the same
`app_id` without needing a new row or endpoint.

## API Contract

No new or changed endpoints — reuses the existing generic settings endpoints as-is:

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/users/{user_id}/settings/frontend` (existing) | Header `X-API-Key: <user's api key>` | `{"settings": "<json string or null>", "updated_at": "..."}` | `403` if the API key does not belong to `user_id` and lacks `users.update`; `500` on DB error |
| `POST /api/users/{user_id}/settings/frontend` (existing) | Header `X-API-Key`; body `{"settings": "<json string>"}` | `{"status": "ok"}` | `403` as above; `500` on DB error |

Both endpoints already exist and are unchanged (`services/music_manager/routers/users.py:889-919`); this
feature is purely a new consumer on the frontend side. Since `settings_json` is a single blob per
`app_id`, all frontend code that reads/writes it must **read-merge-write** (fetch current settings,
merge the `favoriteGenres` key into the parsed object, then POST the whole object back) rather than
overwriting wholesale, so unrelated future keys under `app_id = 'frontend'` are never clobbered by an
unrelated write.

## Cross-App Impact

None. This only touches `services/frontend`; the backend endpoint already exists and is unchanged, and
no other consumer (`Ultrasonic`, LMS/`muma` proxy) uses `app_id = 'frontend'`.

## Frontend Implementation (`services/frontend/src/lib/store.js`)

- `favoriteGenres` (existing `writable([])`, persisted to `localStorage` as `lms_favorite_genres`) keeps
  its current behavior as the source of truth for the UI and for logged-out users.
- On the existing `mumaUser` hydration paths (page-load hydrate, login, logout — all already funnel
  through `mumaUser.set(...)` in `store.js`/`LoginPage.svelte`/`Management.svelte`/`ProfileButton.svelte`),
  add a `mumaUser` subscriber that, when a user with an `id` becomes active:
  1. `GET /api/users/{id}/settings/frontend`.
  2. If `settings.favoriteGenres` exists, replace the local `favoriteGenres` store with it (account wins,
     per functional flow "account favorites take precedence").
  3. If no settings row exists yet (`settings: null`) but the local store is non-empty, treat this as the
     one-time upload case: keep the local value and immediately `POST` it so the account adopts it.
  4. On logout (`mumaUser` set back to `null`), reset `favoriteGenres` to `[]` so a shared/public browser
     doesn't keep showing the previous account's favorites to the next (anonymous) user.
- Add a `favoriteGenres` subscriber, active only while a `mumaUser` with an `id` is set, that debounces and
  `POST`s the read-merge-write update described above whenever the store changes (covers both
  `Dashboard.svelte`'s `toggleFavorite` and the one-time upload in step 3). Guard against POSTing back the
  same value that was just loaded from the server (step 2) to avoid a redundant write on login.
- No changes needed in `Dashboard.svelte`/`Sidebar.svelte` — they already read/write `favoriteGenres`
  via the store and get the new sync behavior for free.

## Technical Acceptance Criteria

1. `GET /api/users/{id}/settings/frontend` for a user with previously-saved favorites returns them, and
   the frontend applies them to the `favoriteGenres` store on load (verified manually against the running
   test stack, and/or a Playwright check alongside the existing `frontend-browser.sh` suite).
2. Toggling a favorite while logged in results in a `POST /api/users/{id}/settings/frontend` call whose
   body's `favoriteGenres` reflects the new state.
3. A user with local-only favorites and no server-side row gets that local value uploaded on first login
   (verified by asserting the `POST` fires once with the pre-existing local value, not an empty array).
4. Logged-out (anonymous) use makes no calls to `/api/users/*/settings/frontend`.
5. Logging out clears `favoriteGenres` back to `[]`.
6. `services/frontend`'s existing lint/typecheck (`scripts/test/frontend-unit.sh`) passes with no new
   errors.

## Related Docs

- [docs/api-specification.md](../../api-specification.md) — existing `/api/users/{id}/settings/{app_id}`
  contract (unchanged by this feature; frontend is a new consumer).
