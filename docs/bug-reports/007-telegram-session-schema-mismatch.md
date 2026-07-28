# Telegram Worker Crashes Loading Session File (SQLite Schema Version Mismatch)

# status: fixed

# reported problem
While sweeping production logs for issues, the `telegram_worker` container was found to be
crashing on startup while loading its Telegram `.session` file (a SQLite database managed by the
`telethon` library), instead of connecting normally.

# Possible reason
`docker/Dockerfile.telegram` ran an **unpinned** `pip install --no-cache-dir telethon` *in addition*
to the pinned `telethon~=1.32.0` already installed from `requirements.txt` by `muma-base`
(`docker/Dockerfile.base`). This second, unpinned install silently overrode the pin with whatever
`telethon` release happened to be latest at build time, making the effective installed version -
and therefore the SQLite schema version that `telethon` writes into the `.session` file - different
and non-reproducible from one image rebuild to the next.

`telethon` bumped its session database schema from version 7 to version 8 starting with release
`1.43.0` (verified directly: `1.42.0` and earlier report `CURRENT_VERSION = 7`, `1.43.0` and later
report `CURRENT_VERSION = 8`), adding a `tmp_auth_key` column to the `sessions` table. A past image
rebuild picked up a `telethon>=1.43.0` release via the unpinned install and upgraded the on-disk
`.session` file to schema version 8. A later rebuild (e.g. after a `pip` cache change, or simply an
older `latest` being resolved again) reverted to an older `telethon` (schema version 7 code, which
only knows a 5-column `sessions` table) trying to read that same, now schema-v8, file - failing
because the code path in `SQLiteSession.set_dc()`/`_upgrade_database()` only runs its ALTER/upgrade
logic when the on-disk version is *older* than `CURRENT_VERSION`; when the on-disk version is
*newer* it is left untouched and the row is read assuming the old, narrower column layout.

# solution
1. Pinned `telethon` in `requirements.txt` to `~=1.44.0` (the latest release, which uses schema
   version 8 - the same version already present in the on-disk production session file), so all
   images consistently install a `telethon` version compatible with the existing session file.
2. Removed the redundant unpinned `RUN pip install --no-cache-dir telethon` from
   `docker/Dockerfile.telegram` entirely, so the Telegram worker image always uses the single
   pinned version resolved by `muma-base`/`requirements.txt`, eliminating the non-reproducible
   double-install that caused the drift in the first place.
3. Verified directly against a locally rebuilt image that `telethon==1.44.0` opens a
   schema-version-8 `.session` file (with a populated `sessions` table including the empty
   `tmp_auth_key` column) without raising an error.
