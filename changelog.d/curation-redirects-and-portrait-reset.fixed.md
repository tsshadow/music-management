- **Rejecting or undoing an artist no longer leaves redirects pointing at it.** Rejecting a name
  with a correction now re-points every redirect that led to it; rejecting it outright or undoing
  it sends those redirects back to the curation queue. Both are listed in the reply. The tagger
  follows a redirect chain to its end (with a loop guard) instead of writing the middle name, the
  Tagger tab refuses a redirect to a rejected artist or one that closes a loop, and
  `GET /api/rules/artists/redirects/issues` reports dangling and looping redirects stored before
  this fix (bug report 080).
- **A cleared artist portrait now disappears everywhere.** The server sync takes back the artwork
  it gave the server for a cleared artist, and the fixed-URL copies (`primary.jpg`, `thumb_*.jpg`)
  are removed on clear and rewritten on selecting another stored image (bug report 080).

<!-- release notes -->

- **Artist curation keeps its redirects consistent.** Rejecting or undoing an artist no longer
  leaves other names pointing at it.
- **Clearing an artist photo sticks.** The photo no longer keeps showing in the player after you
  remove it.
