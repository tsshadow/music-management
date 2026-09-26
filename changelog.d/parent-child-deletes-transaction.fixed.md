- **Deleting a news source or a radio channel, or merging a podcast show, could stop half-way.**
  The music-manager database pool commits every statement on its own, and these three writes ran
  two or three statements in a row with nothing tying them together. A failure in between left a
  news source whose bulletin rows were gone while its recordings stayed on disk, a radio channel
  on air without its history, or a merged-away show still in the queue without any of its
  spellings. Each now runs in one transaction: all of it lands, or none of it does (bug report 113).
<!-- release notes -->
- Deleting a news source or radio channel and merging a podcast show can no longer leave half-done
  data behind when something fails midway.
