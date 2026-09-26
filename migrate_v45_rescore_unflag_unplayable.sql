-- migrate_v45_rescore_unflag_unplayable.sql
--
-- A work that lost its canonical because none of its tracks has a file any more
-- is not a changed version for a curator to review (bug report 100). The first v2-lossless
-- rescore (0.76.0, 2026-09-26) flagged 76,937 such works on the Versies page's "changed" list.
-- Re-runnable: it only clears the review flag where there is no canonical to review.
UPDATE library_works
   SET previous_canonical_track_id = NULL,
       canonical_changed_at = NULL
 WHERE canonical_track_id IS NULL
   AND canonical_changed_at IS NOT NULL;
