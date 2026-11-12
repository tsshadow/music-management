- **A weekly pack from the importer left about 100 tracks a week without a file.** A full scan can
  read a release in `import/<pack>/` before the tagger has split its artists. The importer then
  moves the release out of the pack, and the next scan puts the tagged file on a new track. The
  scan's cleanup could not match the old track to the new one, because the primary artist changed
  and the MP3 and the FLAC were two candidates. On 2026-11-06 one scan left 134 fileless tracks
  this way. The cleanup now also matches on the file name and duration, so the old track's listens
  and ratings move to the new one and the old track goes (GitLab issue #71).
<!-- release notes -->
- Tracks from a weekly release pack no longer stay behind without a file after the import, and
  their listens and ratings move with them.
