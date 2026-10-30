-- rules_scene_group_date_format: scene groups that write a month-first date in their .nfo.
--
-- From migrate_v57_scene_group_date_formats_dot_padded.sql, verbatim (issue #169). These are the
-- only five rows a migration ever inserted; the 29 earlier verdicts on production came from
-- scripts/seed_scene_group_date_formats.py and were never in a migration. INSERT IGNORE on the
-- primary key scene_group keeps any verdict already stored.

INSERT IGNORE INTO rules_scene_group_date_format (scene_group, date_format) VALUES
    ('AOV', 'md'),
    ('BMI', 'md'),
    ('CMC', 'md'),
    ('DDS', 'md'),
    ('SCL', 'md');
