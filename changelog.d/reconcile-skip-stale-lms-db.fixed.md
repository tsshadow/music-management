- **The LMS listen reconcile no longer fails on a stale LMS database.** On production every dry run
  answered 500 with `no such table: user`: besides the live `stable/lms.db`, music-manager also sees
  `alpha/lms.db`, a leftover at LMS schema 114 without a `user` table. A database that lacks one of
  the tables the listen query joins is now skipped with a warning naming the file, and the
  reconcile runs against the rest. See bug report 069.
