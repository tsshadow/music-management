-- migrate_v53_bpm_octave.sql
--
-- Bug report 140, docs/designs/bpm-octave/: which octave of a measured tempo is the track's tempo
-- is now weighed on evidence (services/music_manager/bpm/octave.py) instead of forced into a
-- hand-set genre band, and a person can set a track's tempo by hand.
--
-- library_track_bpm gains the octave choice's inputs and outcome:
--
--   raw_confidence  -- the estimator's own pulse confidence. `confidence` is now that times the
--                      certainty of the octave choice, so a folded or ambiguous value is no
--                      longer "reliable" on the strength of its pulse alone. NULL on rows measured
--                      before this migration; the refold pass fills it from `confidence`.
--   strength        -- the estimator's comb score of the raw estimate,
--   half_score      -- of half of it, and
--   double_score    -- of double it. NULL until the worker measures the row again (the
--                      ambiguous rows first); without them only the priors decide.
--   fold_evidence   -- which evidence decided the octave: estimate, label, artist, genre, band,
--                      path or neutral.
--   fold_margin     -- by how much the winning octave beat the runner-up (log-score units);
--                      below 1 the choice is ambiguous.
--   fold_version    -- the version of the rule (octave.FOLD_VERSION) that chose; the worker
--                      folds rows with an older version again, without re-measuring them.
--
-- library_bpm_priors: per label, per primary artist (own, non-remix tracks only) and per genre,
-- the centre and spread (log2 BPM) of the confident measurements, and how many there were.
-- Derived; the bpm-analyzer recomputes the whole table daily.
--
-- library_track_bpm_manual: a tempo set by hand in the track details (`bpm.override`
-- permission). The effective BPM's first source; the analyzer never writes it. Keyed on
-- track_uid, like library_track_bpm, so it survives a library rebuild.
--
-- library_track_effective_bpm.source gains 'manual', appended to the end of the ENUM so the ALTER
-- is metadata-only and the running release's three values keep their positions.
--
-- Re-runnable: ADD COLUMN IF NOT EXISTS, CREATE TABLE IF NOT EXISTS, and a MODIFY COLUMN that
-- only appends to the ENUM (tests/ci/test_migration_ordering.py, REVIEWED_SAFE). Nothing is
-- refolded here -- the bpm-analyzer does that on its next start.

ALTER TABLE library_track_bpm ADD COLUMN IF NOT EXISTS raw_confidence DECIMAL(4,3) NULL;
ALTER TABLE library_track_bpm ADD COLUMN IF NOT EXISTS strength FLOAT NULL;
ALTER TABLE library_track_bpm ADD COLUMN IF NOT EXISTS half_score FLOAT NULL;
ALTER TABLE library_track_bpm ADD COLUMN IF NOT EXISTS double_score FLOAT NULL;
ALTER TABLE library_track_bpm ADD COLUMN IF NOT EXISTS fold_evidence VARCHAR(16) NULL;
ALTER TABLE library_track_bpm ADD COLUMN IF NOT EXISTS fold_margin FLOAT NULL;
ALTER TABLE library_track_bpm ADD COLUMN IF NOT EXISTS fold_version SMALLINT NULL;

CREATE TABLE IF NOT EXISTS library_bpm_priors (
    kind VARCHAR(8) NOT NULL,
    prior_key VARCHAR(191) NOT NULL,
    centre DOUBLE NOT NULL,
    spread DOUBLE NOT NULL,
    samples INT NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (kind, prior_key)
);

CREATE TABLE IF NOT EXISTS library_track_bpm_manual (
    track_uid VARCHAR(255) NOT NULL PRIMARY KEY,
    bpm DECIMAL(5,2) NOT NULL,
    set_by INT NULL,
    set_at DATETIME NOT NULL
);

ALTER TABLE library_track_effective_bpm MODIFY COLUMN source ENUM('measured', 'tag', 'analyzer', 'manual') NOT NULL;
