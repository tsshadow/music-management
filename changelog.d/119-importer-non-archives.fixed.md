- **The importer no longer tries to extract a video file in the import folder every cycle** (issue
  #90, bug report 119). The extract step handed every file at the root of the import folder to
  patool, whatever it was; two `.mp4` downloads left there produced two WARNINGs and an ERROR per
  file per cycle -- 218 and 109 per file in twelve hours on 2026-09-27. Only a file with an archive
  extension *and* the matching archive signature is extracted now. Anything else -- video, image,
  document, a loose track -- and any archive that cannot be extracted is left where it is, warned
  about once, recorded in `importer_conflicts` with a reason (`migrate_v46` adds the `reason` column
  and the `extractor` step), and skipped until the file changes or disappears. The fallback retries
  log at INFO. Nothing is moved or deleted. `GET /api/import-conflicts` returns the reason, and
  Beheer lists these files next to the folder conflicts as "Openstaande importproblemen".
<!-- release notes -->
- A video or other non-music file in the import folder is now reported once and listed in Beheer,
  instead of raising the same warning and error every five minutes.
