- **LMS now refuses a second user whose login name differs only in case at the schema level.**
  Bug 074's fix stopped the code from creating one, but the `user` table had no index on
  `login_name` at all. Schema version 124 adds a unique index on `login_name COLLATE NOCASE`,
  the collation the login lookup uses, so it also serves that lookup. A database that still holds
  a case variant keeps starting: the index is skipped with an error naming the names, and retried
  on every start until they are merged. Production had no case variants on 2026-09-26 (12 users).
<!-- release notes -->
- LMS now blocks, in its database, a second account whose name differs from an existing one only
  in upper/lower case.
