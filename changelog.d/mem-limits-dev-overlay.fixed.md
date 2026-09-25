- **MariaDB, LMS, Firefox and the rest of production now have a memory ceiling.** Only music-manager
  and the workers had one; on an 8 GB host a runaway LMS scan or a Firefox with full shared memory
  could drag MariaDB into the OOM killer. The limits come from `docker stats` on production
  (2026-09-25): `db` 2g (661 MiB used, 128 MiB buffer pool), `lms` 1536m (549 MiB), `firefox` 2g
  (626 MiB, above its 1 GB `shm_size`), phpMyAdmin 256m, the LMS proxy and autoheal 128m, the
  one-shots 1g and the backup jobs 512m, each overridable in the stack's `.env`. They apply when a
  container is recreated; for `db` that takes a `DEPLOY_DB=1` deploy. Bug report 086.
- **`scripts/dev.sh` starts its stack again.** The dev overlay named an LMS container that is not in
  that stack, and the overlays repeated `security_opt`, which compose 2.26 rejects as a duplicate --
  so neither the dev stack nor README's base + tools combination rendered.
  `tests/ci/test_compose_render.py` now renders every documented compose combination.
<!-- release notes -->
- Every production container now has a memory ceiling, so one runaway service can no longer push
  the database out of memory.
- The local development stack (`scripts/dev.sh`) starts again.
