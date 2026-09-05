-- The artist credit as it read on the file before CleanTagsRule split "feat"/"vs"/"&" into
-- separate `library_track_artists` rows and discarded the joiner word. Display only: never
-- re-parsed, never matched against library_artists, and independent of any curation decision
-- made about the underlying artist names.
--
-- NULL for every existing row. There is no backfill -- the raw joiner text only ever exists
-- transiently during a real tag-write pass, so a file only gains this column the next time it
-- goes through one for some other reason. See docs/designs/artist-curation/functional.md.
ALTER TABLE library_tracks
    ADD COLUMN IF NOT EXISTS display_artist VARCHAR(512) NULL AFTER primary_artist_id;
