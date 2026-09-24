- **A write that replaced a set of rows could leave the set empty.** The database pool runs
  autocommit, so every "delete the old rows, insert the new ones" was two separate commits and the
  `conn.commit()` after it did nothing: a failure in between -- a festival alias longer than the
  column was enough -- left a genre without parents, a festival without aliases (but already
  renamed), a track without artist or genre links, or a rematched listen in both tables. Those
  writes, and the multi-statement account writes (approve/unapprove an access request, delete and
  merge a user), the song pin and split, now run in one explicit transaction via
  `database.transaction()`: all of it lands, or none of it. The scanner now always writes a file's
  links in one transaction, not only when the file moved to another track. Bug report 062.

<!-- release notes -->

- **A failed save could leave genre parents, festival aliases or a track's links empty.** Saves
  that replace a list now land completely or not at all.
