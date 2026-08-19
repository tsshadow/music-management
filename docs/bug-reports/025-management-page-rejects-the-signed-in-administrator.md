# The Management Page No Longer Recognises A Signed-In Administrator

# status: fixed

# reported problem
Since the last releases the web UI's management page misbehaves: it does not always see that you
are signed in as an administrator, and the page itself often does not render. The browser console
shows, in an otherwise working session (the player loads tracks fine):

```
/muma/api/auth/verify:1  Failed to load resource: the server responded with a status of 403 ()
/muma/api/config:1       Failed to load resource: the server responded with a status of 401 ()
```

# Possible reason
Two independent faults, one in the deployment and one in the frontend.

**1. Production had no system API key at all.**

`services/music_manager/api_key.py` resolves the shared system key from `API_KEY` or, failing
that, `MUMA_API_KEY`, and deliberately fails closed when neither is set — that was the point of
removing the hardcoded literal that used to be committed in ten router modules. The production
`.env` does define the key, but spells it `MUMA_API_KEY`; its `API_KEY` entry is empty.
`docker/docker-compose.yml` only ever passed `API_KEY` through, so inside the container both
variables were empty and `is_system_api_key()` returned False for everything.

While the literal fallback still existed this was invisible. Once it was removed, every caller
presenting the system key was rejected. Production logs over 24 hours:

```
14  401 /api/scrobble/event
 7  401 /api/rating/lms-event
 3  403 /api/auth/verify
 3  401 /api/config
```

So this was never only a management-page bug: LMS's scrobble and rating webhooks were being
dropped by the same fault, silently.

The 403/401 split is not two different problems — `routers/users.py:verify_token` answers an
unrecognised key with 403, `routers/config.py:verify_api_key` answers the same key with 401.

**2. The frontend could not recover from a key the backend rejects.**

`Management.svelte`'s `onMount` only attempted its auto-login when there was *no* key at all
(`if (!apiKey && ...)`). A key that is present but rejected therefore skipped the login path on
every single visit, leaving `isLoggedIn` false and the screen stuck on "kan niet verbinden".
`store.js`'s `hydrateMumaUserFromApiKey` had the mirror-image problem: it ignored a non-ok
response, so `mumaUser` stayed null and `isAdmin` silently fell back to the Subsonic `adminRole`
check alone — which is what made the admin state look intermittent rather than simply broken.

Together: the stale key in `localStorage` could never be replaced, so the page stayed broken until
the user cleared their browser storage by hand.

# solution
Deployment: `docker/docker-compose.yml` now passes both `API_KEY` and `MUMA_API_KEY` into the
containers. Compose cannot express a nested `${API_KEY:-${MUMA_API_KEY}}` default (it stops the
default at the first `}` — the same trap already documented on `MUMA_SERVER_SUBSONIC_API_KEY`), so
both spellings are forwarded as-is and the fallback stays in Python where it already was.

Pipeline: `scripts/ci/check-required-secrets.sh` now requires the system key, under either
spelling, in `PROD_ENV_FILE`. That job exists precisely to catch a key going missing from inside a
file-type CI/CD variable, and it was checking only `GOOGLE_CLIENT_ID`.

Frontend: a 401/403 answer to a stored key now drops that key instead of keeping it forever.
`Management.svelte` retries its login with the player's Subsonic credentials once and reloads;
`store.js` clears `mumaApiKey`/`mumaUser`/`userPermissions` so the normal login paths run again. A
5xx or a failed request is explicitly *not* treated as evidence of a bad key — that would log a
user out of a working session over a network blip.

Production was repaired live ahead of the release by filling in the `API_KEY` entry of the
deployed `.env` from the `MUMA_API_KEY` already in it and recreating `music-manager`; the same
value is what LMS presents as `LMS_API_KEY`. `/api/auth/verify` and `/api/config` answer 200 again
over the public URL. The CI/CD variable `PROD_ENV_FILE` still needs `API_KEY` filled in (or the
merged compose change deployed) so the next deploy does not undo it.

Out of scope, still open: the radio poller's `Invalid API key.` against LMS is a separate fault in
the muma→LMS Subsonic auth token, unaffected by this change.
