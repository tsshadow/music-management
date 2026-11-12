- **A star set in the player could stay in LMS and never reach music-manager.** LMS queued the
  rating while it still held the read transaction it had looked the track up in. When another
  connection wrote to `lms.db` in that moment, for example the relay removing the rating it had
  just delivered, SQLite refused the write and LMS logged `Cannot queue the rating ... it is lost`.
  LMS now ends the read before it queues the rating. This also made the rating tests in `muma:e2e`
  and `muma:contracts` fail now and then (issue #242, bug report 160).
<!-- release notes -->
- **A star changed quickly after another one no longer gets lost on its way to the library.**
