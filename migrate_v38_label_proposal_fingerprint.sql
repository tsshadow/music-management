-- migrate_v38_label_proposal_fingerprint.sql
--
-- rules_label_proposals.resolved_fingerprint: what an unplaceable import folder looked like
-- (entries, size, newest mtime), and which catalogue-number rules and decision it was resolved
-- against, the last time the importer read its tags. The mover skips the tag read while the
-- fingerprint still matches. See
-- docs/bug-reports/061-importer-rereads-todo-folders-every-cycle.md.
--
-- NULL means "never resolved under a fingerprint", so every existing row is read once more
-- after this lands and then left alone. Re-runnable: scripts/deploy.sh applies every
-- migrate_*.sql on every deploy.
ALTER TABLE rules_label_proposals
    ADD COLUMN IF NOT EXISTS resolved_fingerprint CHAR(64) NULL;
