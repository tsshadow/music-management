-- migrate_v57_scene_group_date_formats_dot_padded.sql
--
-- Issue #169. NfoDate now reads a date label padded with dots to a column
-- (`Date..........: 11.23.2022`), which AOV, AOV_INT, DDS, CMC and others write.
-- scripts/seed_scene_group_date_formats.py measured the month-first groups before
-- those lines were readable, so it never saw their tokens. The same measurement
-- with the new reader, run on production on 2026-10-03 over the label tree, adds
-- these five groups. The 29 earlier verdicts stay the same.
--
--   AOV  316 tokens month-first, 75 that agree (all year-first, where md and the
--        default read the same)
--   DDS  18 month-first, 0 day-first
--   CMC   7 month-first, 0 day-first
--   BMI   2 month-first, 0 day-first
--   SCL   2 month-first, 0 day-first
--
-- Without these rows, the tagger would read an ambiguous AOV date such as
-- 08.11.2023 as 8 November. Re-running the seed script with --apply gives the same
-- rows. Re-runnable and expand-only: INSERT IGNORE keeps any verdict already stored.

INSERT IGNORE INTO rules_scene_group_date_format (scene_group, date_format) VALUES
    ('AOV', 'md'),
    ('BMI', 'md'),
    ('CMC', 'md'),
    ('DDS', 'md'),
    ('SCL', 'md');
