- **Listen times destroyed by bug 039 can be restored from LMS.** Until migrate_v33 every update
  of a listen -- a rematch, a played-seconds top-up, an account merge -- moved its `listened_at` to
  the moment of that update. LMS's own `listen` table still has the real time of every play it
  relayed. `GET /api/scrobble/reconcile/lms` (admin) compares the two per user and track, joined by
  file path across the `/music` vs `/mnt/music` spellings, and reports `exact` / `shifted` /
  `muma_only` / `lms_only` with a sample; `POST` restores the shifted times (and, on request,
  inserts plays muma lost, as source `lms-reconcile`) in one transaction per user. Idempotent;
  ListenBrainz imports are never touched.

<!-- release notes -->

- Admins can repair listening-history times that an earlier bug moved, using the play times LMS
  kept: a dry run first, then the restore.
