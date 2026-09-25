- **A login typed in another case no longer splits one person into two accounts.** After the
  0.73.1 key rotation the phone was signed in as "Teun" for the account "user". MuMa accepted
  it, because MariaDB compares names case-insensitively. LMS then looked the typed name up byte
  for byte, found nobody, and created a second user, id 13 `Teun`. Every play from the phone
  since 05:05 UTC went to that user (31 listens) and was relayed to MuMa as `Teun`, so the
  history was split for LMS and for everything that groups by name in Python. Account names are
  now case-insensitive everywhere. The login answers with the account's own spelling and every
  client signs in under it. LMS matches login names case-insensitively and never creates a user
  that differs only in case. Creating an account with a case variant of an existing name is a
  409. Scrobbles, ratings, feeds and the reconcile store and compare the canonical spelling. The
  existing fork is repaired by `scripts/prod/repair-username-case.sh`, which is run by hand. See
  bug report 074 and `docs/authentication.md`.

<!-- release notes -->

- **Signing in with your name in another case no longer creates a second account.** Plays made
  that way were filed under a separate user. The login now always uses the account's own
  spelling. A repair script merges the history that was split this morning.
