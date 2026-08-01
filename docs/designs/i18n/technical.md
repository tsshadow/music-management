# Frontend Internationalisation (i18n) — Technical Design

Implements [`functional.md`](functional.md). Scope is `services/frontend` only.

## Data Model

No database change. No new table, no new column.

The chosen language is stored as a `language` key inside the existing per-user app-settings blob:

- Table `user_app_settings` (created in `services/music_manager/routers/users.py`), row keyed by
  `(user_id, app_id = 'frontend')`, payload in `settings_json`.
- That blob today holds exactly one key, `favoriteGenres`. This feature adds a second:

  ```json
  { "favoriteGenres": ["techno", "ambient"], "language": "nl" }
  ```

- `language` is a lowercase ISO 639-1 code, one of `"en"` or `"nl"`. Any other value found in the blob is
  ignored and treated as absent.

Browser-local storage: `localStorage` key `muma_locale`, holding the same JSON-encoded code. The write lives
in `src/lib/i18n/index.js` rather than reusing `store.js`'s private `persist()` helper: `store.js` imports
the i18n module for the account sync, so the reverse import would be a cycle.

Only a language the *user* picked is written to `localStorage`. A language applied from the account is not,
which is what makes logout able to fall back to this browser's own preference instead of keeping the
previous user's.

## API Contract

No new or changed endpoints. The feature reuses the generic per-user app-settings endpoints exactly as
`favoriteGenres` already does.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/users/{user_id}/settings/frontend` | Header `X-API-Key`; no body | `{"settings": "<json string>"}`; `settings` is `null` when the user has never saved any | Non-2xx or network failure: the frontend keeps the local language and logs a warning; nothing surfaces to the user. `403` when the caller is neither the user nor holder of `users.update` |
| `POST /api/users/{user_id}/settings/frontend` | Header `X-API-Key`, `Content-Type: application/json`, body `{"settings": "<json string>"}` — the full blob, read-merge-written so sibling keys survive | 2xx, body ignored | As above: failures are logged and swallowed; the local language stays applied |

## Frontend Architecture

### Module layout

```
services/frontend/src/lib/i18n/
  index.js            # locale store, t store, lookup, interpolation, supported-locale list
  locales/en.json
  locales/nl.json
```

### `src/lib/i18n/index.js`

- `SUPPORTED_LOCALES` — `[{ code: 'en', label: 'English' }, { code: 'nl', label: 'Nederlands' }]`.
  `DEFAULT_LOCALE` is `'en'`.
- Dictionaries are loaded with `import.meta.glob('./locales/*.json', { eager: true })`. Eager, not lazy:
  two files of a few kilobytes each, and a synchronous `t` avoids a flash of missing text on first paint
  and avoids async setup in unit tests. If the locale count grows materially this becomes lazy loading, at
  which point `t` gains a "dictionary not loaded yet" path — deliberately not built now.
- `locale` — store initialised by `resolveInitialLocale()`; `locale.set(code)` applies *and* persists to
  `muma_locale`. Setting it to an unsupported code is ignored (the store keeps its previous value), so a
  stale account value or a corrupted stored one cannot blank the interface.
- `setLocaleFromAccount(code)` — applies a language without persisting it, used by the account sync.
  `resetLocaleToBrowser()` re-runs `resolveInitialLocale()`, used on logout.
- `currentLocale()` — reads the active locale outside a component, for the sync code in `store.js`.
- `resolveInitialLocale()` — first supported hit wins: `localStorage` (`muma_locale`) →
  `navigator.language` primary subtag (`'nl-BE'` → `'nl'`) → `DEFAULT_LOCALE`. The account value is not
  consulted here; it arrives later, asynchronously, once the user hydrates (see below).
- `t` — `derived(locale, ...)` returning a `(key, vars) => string` function, so components use
  `{$t('a.b.c')}` and re-render on locale change.
- Lookup: the key is split on `.` and walked through the active dictionary. A miss, or a hit that is not a
  string, falls back to the same key in `en`; a miss there returns the key itself, plus a single
  `console.warn` guarded by `import.meta.env.DEV`.
- Interpolation: `{name}` placeholders replaced from the `vars` object. A placeholder with no matching var
  is left as-is rather than rendered as `undefined`.
- Side effect: a `locale` subscription sets `document.documentElement.lang`.

### Translation file convention

Nested objects keyed `<area>.<component>.<thing>`, e.g.:

```json
{ "settings": { "language": { "title": "Language", "help": "..." } } }
```

Both files carry the same key set; `en.json` is the reference. Values are plain strings — no plurals or
date/number formatting in this iteration. Existing `toLocaleString('nl-NL')` calls scattered through the
components are left alone and are explicitly out of scope.

### Account sync (`src/lib/store.js`)

`store.js` currently implements load-on-hydrate / debounced-save / clear-on-logout hardcoded around
`favoriteGenres`. Language needs the identical lifecycle against the same blob, so the read-merge-write is
extracted rather than duplicated:

- `loadFrontendSettings(userId)` → parsed blob object, or `null` on any failure or malformed JSON.
- `saveFrontendSetting(userId, key, value)` → re-reads the blob, sets `key`, writes the whole blob back.
  Existing behaviour, generalised over the key.

`favoriteGenres` is rerouted through both helpers; its observable behaviour does not change. Language then
mirrors it:

- On `mumaUser` gaining an `id`: `applyAccountSettings(userId)` reads the blob **once** and applies both
  keys from that single response. A valid `language` goes through `setLocaleFromAccount` (guarded by an
  `applyingAccountSettings` flag so the write is not echoed straight back to the server). No `language` on
  the account means the current local value is uploaded, so a pre-login choice is not lost.
- On `locale` change while a synced user is active: debounced save (400 ms, matching favourite genres).
- On logout (`mumaUser` → `null`): the synced-user id is cleared, favourites are emptied and
  `resetLocaleToBrowser()` runs, so the next person using the browser does not inherit the previous user's
  language. Sessions authenticated with the shared system key (no `user.id`) are left untouched, as
  favourite genres already do.

### Language setting UI

`src/lib/settings/LanguageSetting.svelte` — a `<select>` bound to the `locale` store, options from
`SUPPORTED_LOCALES` with each label in its own language — mounted at the top of the Interface section of
`src/lib/settings/GeneralSettings.svelte`. It is its own component rather than inline markup so it can be
tested without mounting the whole settings screen (which fetches the Subsonic user on mount). Styled per
[docs/styleguide.md](../../styleguide.md) form-control rules (`bg-[#282828]`, subtle border,
`focus:border-[#1DB954]`, `rounded`).

It is deliberately *not* routed through `/rest/updateUser` alongside the other fields on that screen: the
language is a frontend preference, not an LMS user field, and it saves on change rather than on that
screen's Save button.

Its own label and help text are the first `$t` consumers, which makes the picker the working smoke test of
the mechanism. The rest of the strings on that screen stay hardcoded.

## Cross-App Impact

None. `services/frontend` only. No `music_manager` change, no LMS/`muma` proxy change, no Ultrasonic change.
Ultrasonic has its own Android resource-based localisation and is untouched; the `language` key added to the
`frontend` app-settings blob is namespaced to `app_id = 'frontend'` and invisible to it.

## Technical Acceptance Criteria

1. `t('settings.language.title')` returns the English string with `locale` set to `en`, and the Dutch
   string with `locale` set to `nl`.
2. `t('greeting', { name: 'Teun' })` interpolates `{name}`; a placeholder with no matching var is left
   verbatim in the output.
3. A key present in `en.json` but absent from `nl.json` returns the English value while `locale` is `nl`.
4. A key absent from every dictionary returns the key string itself and does not throw.
5. Setting `locale` to an unsupported code leaves the previous locale in effect.
6. `resolveInitialLocale()` returns the stored value when `localStorage` holds a supported code; otherwise
   the `navigator.language` primary subtag when supported; otherwise `en`.
7. `saveFrontendSetting(userId, 'language', 'nl')` issues a `GET` then a `POST` whose body preserves a
   pre-existing `favoriteGenres` value in the same blob.
8. `loadFrontendSettings` returns `null` — and does not throw — on a non-2xx response, a network rejection,
   and a malformed `settings` string.
9. Hydrating a user whose account blob has `language: 'nl'` sets `locale` to `nl` and does not trigger a
   save back to the server.
10. Hydrating a user whose account blob has no `language` uploads the current local locale.
11. Setting `mumaUser` to `null` resets `locale` away from the account value.
12. Tests live in `services/frontend/tests/unit/i18n.test.js` (mechanism),
    `services/frontend/tests/unit/languageSetting.test.js` (picker) and extend
    `services/frontend/tests/unit/store.test.js` (sync helpers), matching the existing vitest layout, and
    pass under `npm run test:unit`.
13. `npm run lint`, `npm run check` and `./scripts/test/frontend-unit.sh` pass.

## Related Docs

- [docs/designs/favorite-genres/technical.md](../favorite-genres/technical.md) — the per-user app-settings
  sync pattern this feature reuses and generalises.
- [docs/styleguide.md](../../styleguide.md) — form control styling.
- [docs/api-specification.md](../../api-specification.md) — the user app-settings endpoints.
