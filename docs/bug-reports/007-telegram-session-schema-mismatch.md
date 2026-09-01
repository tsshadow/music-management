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

**Second, compounding bug found while verifying the fix on production**: after deploying the code
change above through a full green `release/*` pipeline (including `muma:deploy`), the running
`muma-telegram-worker` container on production was still the exact same 13-day-old image and still
crashed with a (slightly different) unpack error. `scripts/ci/build-and-push-images.sh` - the script
introduced to fix an earlier, analogous problem for `music-manager`/`lms` (see `CHANGELOG.md` 0.0.2)
- only ever built and pushed those two images. It never covered `muma-base`, `muma-downloader`,
`muma-telegram`, `muma-importer`, or `muma-tools` (the images `docker/docker-compose.yml` actually
uses for the Telegram/SoundCloud/YouTube/importer workers and CLI tools). `muma:deploy`'s
`docker compose pull` therefore only ever re-pulled whatever `:latest` tag had last been pushed
*manually* (via the local-only `build.sh`/`publish.sh` scripts) - so this code fix, despite a fully
green pipeline, would never have actually reached production.

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
4. Extended `scripts/ci/build-and-push-images.sh` to also build and push `muma-base`,
   `muma-downloader`, `muma-telegram`, `muma-importer`, and `muma-tools` (in addition to
   `music-manager`/`lms`), so every image `docker/docker-compose.yml` references on production is
   kept in sync by every `release/*` pipeline, closing this deployment gap for good.
