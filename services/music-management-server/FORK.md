# The LMS fork

`services/music-management-server` is a **hard fork** of [LMS (Lightweight Music Server)](https://github.com/epoupon/lms)
by Emeric Poupon. It is not a patch set on top of upstream and is not kept in sync with it: upstream
changes come in only as deliberate, individual ports. This file records where the fork started, what
is ours, how the database versions of the two lines relate, and how to port an upstream fix.

## Upstream base

| | |
|---|---|
| Upstream repository | https://github.com/epoupon/lms (branch `develop`, releases tagged `vX.Y.Z` on `master`) |
| Base release | **v3.76.0** |
| Base tag commit | `d3eb168d73e498310c801ac09fd140594648a016` ("Merge branch 'develop' for release v3.76.0", 2026-03-14) |
| Commit actually merged | `351c412dd325d6d9730271f9487bb5cdb05ec1cd` ("Bumped Wt version", upstream `develop`, 2026-03-14) -- same tree as the tag (`17a49a7035db`) |
| Merged into the fork by | `0cdff5a51` "Merge upstream/develop into develop and resolve conflicts" (2026-05-01) |
| Upstream database version at the base | **103** (`LMS_DATABASE_VERSION{ 103 }`) |
| Last upstream checked | v3.79.0 (database version 110); `develop` at 3.81.0 (database version 116), 2026-09-25 |

How this was established: the fork's history was imported into the monorepo as a subtree
(`073990b7c`, `git-subtree-split: 520101530`). In that history the last upstream commit is
`351c412dd`, reached through the merge `0cdff5a51`; every commit after it is the fork's own. Its tree
is identical to the upstream tag `v3.76.0`, and `CMakeLists.txt` there reads `project(lms VERSION 3.76.0)`.
The local checkout is shallow, so this history is only visible in a full clone
(`git clone --filter=blob:none` of the GitLab project, or `git fetch --unshallow`).

**The version number in `CMakeLists.txt` is the fork's own.** It reads `3.83.1`; the fork bumped it
from 3.78.1 onwards on its own (July 2026) and it has not moved since the monorepo import. It does
not mean "upstream 3.83.1" -- fork 3.79.0 and upstream v3.79.0 are unrelated. The upstream base is
v3.76.0, whatever the project version says. MuMa releases are versioned by the monorepo's `VERSION`.

Before the 2026-05 merge the fork (then `muma/lms`, later `muma/music-server` on the
self-hosted GitLab) had tracked upstream `develop` since December 2023; `0cdff5a51` is the last time
upstream was merged wholesale. Nothing is merged wholesale any more.

## How far it has diverged

Against v3.76.0: 165 files under `src/` are new (of which ~60 are the Svelte UI and 37 a vendored
rapidjson), and 431 upstream files are modified -- many of them by the ID type-safety refactor
(`6f05d13d3`) and the formatting pass, which touch nearly every database object and Subsonic
endpoint. No upstream file has been deleted. Expect an upstream patch to conflict on context even
where the logic it changes is untouched here.

## MuMa-specific subsystems and files

Wholly ours (new files; upstream has no counterpart):

| Subsystem | Files |
|---|---|
| `/muma` resource: auth, admin routes, MuMa reverse proxy | `src/libs/muma/` (`MumaResource`, `Authentication`, `PathEncoding`, `Routing`) |
| Accounts from music-manager | `src/libs/services/auth/impl/musicmanagement/` (`MusicManagementPasswordService`, `UserSynchronizer`, `MumaUserSync.hpp`), `src/libs/services/auth/include/services/auth/IUserSynchronizer.hpp` |
| Listen relay to music-manager | `src/libs/services/scrobbling/impl/musicmanagement/` |
| Rating relay to music-manager | `src/libs/services/feedback/impl/musicmanagement/` |
| HTTP client hardening (retry policy, proxy continuation, concurrency gate) | `src/libs/core/impl/http/RetryPolicy.*`, `ProxyContinuation.cpp`, `ProxyState.hpp`, `src/libs/core/include/core/http/ProxyContinuation.hpp`, `src/libs/core/*/ConcurrencyGate.*`, `src/libs/core/*/Md5.*` |
| Spotify-style Subsonic extensions (`getSpotify*`, dedupe/paging, memories, festival line-ups, songs by path, scan scope) | `src/libs/subsonic/impl/endpoints/Spotify.*`, `SpotifyPaging.hpp`, `Memories.*`, `FestivalLineupRepository.*`, `SongsByPath.*`, `ScanScope.*`, `UserSettingsValidation.hpp`, `src/libs/subsonic/impl/AuthCache.*` |
| Scan lanes (quick/full scan schedule, request collector) | `src/libs/services/scanner/impl/ScanRequestCollector.*`, `ScanSchedule.*`, `ScanStepSequence.*`, `ScanStepScanFiles.cpp` |
| MuMa web UI (Svelte) | not in this tree: `services/frontend`, copied into `docroot/spotify` by `Dockerfile-release` and served by `SpotifyResource` (`src/lms/main.cpp`) |
| Vendored JSON | `src/libs/rapidjson/` |

Ours inside upstream files (modified, not new) -- the places a port most often lands on:

- `src/libs/database/impl/Migration.cpp` -- steps 103 to 126 (versions 104 to 127), see below.
- `src/libs/database/include/database/objects/User.hpp` -- `muma_id`, `muma_scrobbling_enabled`,
  web-player settings, `disabled`; `Track.hpp` -- `rating`, `play_count`, song-version columns, `bpm`
  (the file's BPM tag, step 125); `ScanSettings.hpp` -- `release_artwork_rules` (step 126).
- `src/libs/subsonic/impl/SubsonicResource.cpp` -- auth cache, `spotify/*` and MuMa endpoint
  registration; `endpoints/UserManagement.cpp` -- self-service `updateUser`.
- `src/libs/subsonic/impl/ParameterParsing.*` -- `parameterMapToDebugString`, moved out of
  `SubsonicResource.cpp`, also redacts `t` and `s`, and the credentials inside a value that is a
  URL itself (bug report 150).
- `src/lms/main.cpp` -- wiring of the MuMa services, the `/muma` resource and the user sync.
- `src/libs/services/scrobbling/impl/ScrobblingService.cpp`, `feedback/impl/FeedbackService.cpp`
  -- the always-on MuMa relay next to the configured backend.
- `src/libs/services/scanner/impl/steps/ScanStepAssociateArtistImages.cpp` -- keeps an artist's
  artwork when it is an image under `artist-image-managed-directory` (music-manager's portraits,
  bug report 139).
- `src/libs/services/scanner/impl/steps/ScanStepAssociate*.cpp`, `ScanStepComputeClusterStats.cpp`
  -- a scoped scan walks only its `ScanScope` (new file `steps/ScanScope.*`), not the whole
  library (bug report 141).
- `src/libs/services/scanner/impl/steps/ScanStepAssociateReleaseImages.cpp` -- after the
  preferred cover names and the embedded front cover, a scene-style `00-...` image or the only
  image of the folder (new file `steps/ReleaseArtworkRules.*`, keys `cover-fallback-*` and
  `cover-single-image-fallback`). The last scan's `scan_settings` row records a fingerprint of
  those rules (`release_artwork_rules`, step 126); a library-wide scan that finds it changed
  recomputes all release, artist and track artwork without re-reading files. Bump
  `releaseArtworkRulesCodeVersion` when the way the rules are applied changes (bug report 144).

## Database version policy

The schema version is one integer (`version_info.db_version`), and `doDbMigration()` walks it one
step at a time: `migrateFromV<n>` takes a database from `n` to `n + 1`, and every step must exist.
Two lines numbering the same integer independently cannot be merged by number.

That collision is already real. The fork's `migrateFromV103` (track rating) and upstream's
`migrateFromV103` (MusicNN embeddings) are different migrations, and upstream's 104-115 differ from
ours in every case. A production database at version 121 has run **our** 103-120, none of
upstream's.

The policy:

1. **Steps 33-102 (up to version 103) come from upstream v3.76.0**, but are not byte-identical to
   it. The fork edited them in place: the historical `track` rebuilds carry a `rating` column, the
   ID refactor (`6f05d13d3`) dropped the `user` foreign keys of `rated_*`, `ui_state`, `playqueue`
   and `tracklist` (users are referenced by plain id throughout the fork), and `migrateFromV102`
   wraps its index creation in a try/catch. Compare against the fork's text, not upstream's, when
   porting anything that touches these tables.
2. **Everything from 103 up is the fork's own sequence**, contiguous, owned by this repository
   alone. `LMS_DATABASE_VERSION` is the version a fresh migration run ends at, so the next free
   step is `migrateFromV<LMS_DATABASE_VERSION>` (today: `migrateFromV127`, taking 127 to 128).
3. **An upstream migration is ported, never merged under its own number.** It becomes the fork's next
   free step, and its function carries a comment naming the source:
   `// Port of upstream LMS migrateFromV108 (v3.78.0, <commit>)`. Add it to the table below.
4. **A port is idempotent.** Upstream wrote it against upstream's schema at that point, which is not
   ours: guard `ADD COLUMN` (`try`/`catch`, as `migrateFromV104` does), use `IF NOT EXISTS` for
   tables and indexes, and check that a table it alters exists here at all.
5. **Never renumber a deployed step.** Production and every dev database have recorded the number.
6. **An offset for upstream numbers was considered and rejected.** Reserving a range (say, fork
   steps at 1000+) would only work with a second version counter and a driver that runs two
   sequences; one linear sequence with a mapping table is simpler, and a port has to be rewritten
   for our schema anyway (rule 4).

A branch that adds a migration therefore also checks that no other open branch has claimed the same
step -- two branches both adding step 122 is the same collision in miniature. Whichever merges
second renumbers before merging.

### Upstream migrations ported so far

| Fork step | Upstream step | Upstream release | What |
|---|---|---|---|
| -- | -- | -- | none yet |

No upstream step above 102 has been ported. Upstream 103 (MusicNN embeddings), 104 (playlist-file
artwork), 105 (Last.fm keys), 106 (MBID columns to BLOB) and later exist only upstream. (Fork steps
104 and 105 say "Upstream now also added rating"; upstream has no `track.rating`. Step 104 repeats
our own step 103 idempotently and 105 is empty -- leftovers of the 2026-05 merge, not ports.)

## Porting an upstream fix

1. Find the fix upstream (`https://github.com/epoupon/lms/commits/develop`) and read the whole
   commit: upstream fixes often ride on a refactor landed a few commits earlier.
2. Fetch it without disturbing the monorepo:
   ```bash
   git fetch https://github.com/epoupon/lms <sha>
   git format-patch -1 <sha> --stdout > /tmp/upstream.patch
   ```
3. Apply it under the fork's directory, on a branch off `develop`:
   ```bash
   git apply --3way --directory=services/music-management-server /tmp/upstream.patch
   ```
   `git cherry-pick` does not work here -- upstream paths are relative to its repository root, ours
   sit under `services/music-management-server/`. Expect context conflicts (see "How far it has
   diverged"); resolve by hand against the fork's version.
4. If the fix contains a migration, apply the [database version policy](#database-version-policy):
   next free fork step, idempotent, source comment, table row above.
5. Run `./scripts/test/muma-server-unit.sh`, `./scripts/test/muma-server-tidy.sh` and
   `./scripts/test/muma-server-format.sh --fix`. An upstream file brought in whole may raise
   clang-tidy findings the baseline does not hold; fix them rather than accept them.
6. Name the upstream commit in the commit message (`port(server): <subject> (upstream <sha>)`) and
   add a changelog fragment.

Do not merge upstream `develop` wholesale. The last such merge (`0cdff5a51`) needed a follow-up
"Fix compilation error ... by using upstream API" and the database collision above.
