- **The importer sends one phone notification per release instead of one per file.** A 44-release
  weekly pack used to be well over a hundred pushes. Each release now gets one `Import Complete`
  push with its label, catalogue number and track count. Every imported track is still in the event
  log as an `INFO` event (`Track Imported`), just without a push.

<!-- release notes -->

- **One notification per imported release** (label, catalogue number, number of tracks) instead of
  one per track. The individual tracks are still in the event log.
