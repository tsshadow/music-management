# Mobile sign-out and Google sign-in — Technical Design

Implements [functional.md](functional.md). Bug report:
[106](../../bug-reports/106-mobile-sign-out-and-google-sign-in.md).

## Data Model

No database change. One new browser `localStorage` key:

| Key | Store | Meaning |
|---|---|---|
| `muma_signed_out` | `signedOut` in `services/frontend/src/lib/store.js`, persisted with `device: true` | Set by a deliberate logout, cleared by the next successful sign-in. A device store so `resetSessionState()` does not wipe it. |

Native storage is unchanged; sign-out still clears it through `ActiveServerProvider.signOut()`
(`Settings.staticPassword`, `mumaApiKey`, `mumaUserId`, and `SecureSettings.clear()` -- which covers
the MuMa access/refresh tokens and the Subsonic token from !1034).

## API Contract

No HTTP change. The Capacitor bridge (`MumaSystem` plugin) contract, shared between
`services/muma-mobile` and `services/frontend/src/lib/platform/`:

| Method | Request | Response | Error cases |
|---|---|---|---|
| `signOut` (changed) | none | resolves once credentials and queue are cleared | rejects only when the credential store itself throws. Runs on the main thread now; a queue failure is logged and does not reject. |
| `googleSignInAvailable` (new) | none | `{available: boolean}` -- a real `BuildConfig.GOOGLE_WEB_CLIENT_ID` (not blank, not `placeholder-id`) | none |
| `googleSignIn` (new) | none | `{idToken}` | rejects with `code` `not-configured`, `cancelled`, `no-credential`, or `failed` (message = exception class name) |

`platform.system` gains `googleSignInAvailable(): Promise<boolean>` (browser: `false`; shell: bridge
failure reads as `false`) and `googleSignIn(): Promise<string|null>` (shell: `cancelled` becomes
`null`; browser: rejects `not-configured`). Not breaking: both are additions, and `signOut` keeps
its shape.

### The sign-out path

1. `ProfileButton.handleLogout` awaits `platform.system.signOut()`, bounded at 5 s.
2. Shell: `MumaSystemPlugin.signOut` runs `SessionSignOut.run` on `Dispatchers.Main` via
   `PluginCallScope`: credentials first, then `MediaPlayerManager.clear()`. The old code called
   `clear()` on Capacitor's plugin thread; Media3's `MediaController` throws
   `IllegalStateException` off its application thread, Capacitor rethrows plugin exceptions
   (`Bridge.callPluginMethod`: "Serious error executing plugin" → `RuntimeException`), so the call
   never settled and the credentials were never cleared.
3. The page flushes pending settings (bounded), resets every persisted store, then sets
   `signedOut = true`, then reloads.
4. On boot, `restoreSession` sees `signedOut`, asks the phone to sign out once more (best effort)
   and returns `false` without reading the phone's credentials -- the login page appears.
5. `signIn()` in `login.js` and a successful Google sign-in on `LoginPage` clear `signedOut`.
6. `RESTMusicService.refreshSubsonicToken` drops a token answer that arrives after the password was
   cleared, so a refresh started at boot cannot write the Subsonic token back after a sign-out.

### The Google path in the shell

`LoginPage` inside the shell never loads Google Identity Services. On mount it asks
`googleSignInAvailable()`; when true it renders the style-guide button, whose click calls
`googleSignIn()` and passes the token to the existing `handleGoogleResponse` (same
`POST /api/auth/google`, same access-request screens). On `status: "ok"` it also calls
`saveCredentials({url, username, password: api_key})` -- closing the "known gap" the old comment
described -- so native playback, downloads and Android Auto share the session.

Natively (`capacitor/GoogleSignIn.kt`): `CredentialManager.getCredential` with
`GetSignInWithGoogleOption(BuildConfig.GOOGLE_WEB_CLIENT_ID)` (bug report 011), the credential
parsed from `CustomCredential` with `GoogleIdTokenCredential.createFrom` (bug report 013). The
token's audience is the Web client ID, which is what `_verify_google_id_token()` verifies -- no
backend change.

## Cross-App Impact

`services/muma-mobile` (plugin, new helpers) and `services/frontend` (platform adapters, LoginPage,
ProfileButton, nativeSession, store, login) change together in one commit (AGENTS.md rule 7). No
backend change. Google Cloud Console must hold an Android OAuth client for
`nl.teunschriks.mumamobile` with the release certificate SHA-1 (bug report 011); that is outside the
repository.

## Technical Acceptance Criteria

1. `MumaSystemPluginSignOutTest`: called from a background thread, `signOut` clears credentials and
   queue on the main thread and resolves; a failing queue still clears credentials and resolves.
2. `SessionSignOutTest`: credentials before queue; queue failure returned, not thrown; credential
   failure thrown.
3. `GoogleSignInTest`: `isConfigured` rejects blank/placeholder; failure codes map; only a Google
   `CustomCredential` yields a token.
4. `profileButtonLogout.test.js`: a never-answering native sign-out still logs out after the bound;
   `muma_signed_out` survives the reset.
5. `nativeSession.test.js`: with `signedOut` set, `restoreSession` returns `false`, never reads the
   phone's credentials, calls `signOut` again; `signIn` clears the marker.
6. `loginPageNativeGoogle.test.js`: button only when available; no GSI script in the shell; token →
   `/api/auth/google` → session + `saveCredentials`; cancel is silent; refusals are worded.
7. `platformCapacitor.test.js`: adapter mapping of the two new methods.

## Related Docs

- [authentication/technical.md](../authentication/technical.md) -- MuMa Mobile section updated.
- [docs/deployment.md](../../deployment.md) -- "Google Sign-In on MuMa Mobile (Android)".
- Bug reports 011, 013, 019, 020 (the earlier native Google sign-in history).
