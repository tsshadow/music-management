- **A script cleans up the 1,019 tracks the import packs left without a file.**
  `tools/relink_fileless_backlog.py` moves the listens and ratings of a fileless track to the one
  track with a file that has the same title and a duration within 5 ms (604 on production on
  2026-11-12). It then deletes the fileless tracks that have no listen, rating, pin or reviewed
  label (256), and lists the 159 that are left for a person. It is a dry run unless `--apply` is
  given, writes a JSON backup before the first write, and `--rollback` restores that backup
  (GitLab issue #71).
<!-- release notes -->
- Old tracks without a file from the weekly release packs can now be cleaned up, with their
  listens and ratings moved to the track that has the file.
