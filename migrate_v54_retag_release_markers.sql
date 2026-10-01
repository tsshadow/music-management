-- migrate_v54_retag_release_markers.sql
--
-- Bug report 142, docs/designs/release-series-markers/: the tagger read release and series
-- markers in download titles as the artist/title split ("Luner - Holding On To You ｜ Q-dance
-- presents SPEQTRUM" became artist Q-dance, title SPEQTRUM), and a featured artist swallowed
-- the remix bracket behind it ("Fired Up Ft. The Kemist (Kayzo Remix)" became "Fired Up").
-- The code is fixed; this queues the files already tagged that way, once, for the tagger.
--
-- Only the affected files: the patterns below are the markers the fix reads, matched on the
-- file name, which is the upload's original title. Not the whole Youtube or Soundcloud tree --
-- see the notes on migrate_v7, whose tree-wide requeue on every deploy starved the API.
--
-- Recovery needs nothing else. The tagger works the queue (reason 'release_marker'), its
-- write changes the file's mtime, the scanner reads it again, and a changed title or
-- primary artist gives the file a new track row (routers/scanner.py), which has no work yet:
-- the song-version worker groups it under the new key within the hour.
--
-- Re-runnable and expand-only: an UPDATE of rows that already exist, nothing else. tools/
-- apply_migrations.py skips this file while its hash is unchanged, so it runs once; a forced
-- re-run re-queues the same bounded set and nothing more. A file already on the queue keeps
-- its reason and its failure count (needs_rescan = FALSE).
--
-- tagger_processed_files and its rescan_reason/attempts columns come from migrate_v7, v16 and
-- v37, which run before this file.

UPDATE tagger_processed_files
SET needs_rescan = TRUE, rescan_reason = 'release_marker', attempts = 0, last_attempt = NULL
WHERE needs_rescan = FALSE
  AND (
        -- "(Gearbox Presents Lockdown 3.0)", "[DRS Presents： TSR Album 8.0 - TSR042]"
        LOWER(filepath) LIKE '%(% presents %)%'
     OR LOWER(filepath) LIKE '%[% presents%]%'
        -- "｜ Q-dance presents SPEQTRUM"
     OR LOWER(filepath) LIKE '%｜% presents %'
        -- "(Dungeon： The Mini Album)"
     OR LOWER(filepath) LIKE '%(%：%)%'
     OR LOWER(filepath) LIKE '%[%：%]%'
        -- non-song uploads and channel series
     OR LOWER(filepath) LIKE '%｜ interview with %'
     OR LOWER(filepath) LIKE '%｜ cover by %'
     OR LOWER(filepath) LIKE '%｜%preview%｜%'
     OR LOWER(filepath) LIKE '%/101barz/%'
        -- "Fired Up Ft. The Kemist (Kayzo Remix)": a feature in front of a remix bracket
     OR LOWER(filepath) LIKE '% ft. %(% remix)%'
     OR LOWER(filepath) LIKE '% feat. %(% remix)%'
     OR LOWER(filepath) LIKE '% ft. %(% edit)%'
     OR LOWER(filepath) LIKE '% feat. %(% edit)%'
     OR LOWER(filepath) LIKE '% ft. %(% bootleg)%'
     OR LOWER(filepath) LIKE '% feat. %(% bootleg)%'
  );
