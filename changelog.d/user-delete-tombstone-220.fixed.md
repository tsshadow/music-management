- **A new account with the name of a deleted one got its ratings and listens.** Ratings, listens,
  unmatched listens, ListenBrainz imports and feeds are keyed by username, and a delete left them
  in place. A delete now moves them to `deleted-<id>` in the same transaction, so the server totals
  keep them and the new account starts empty. No account can take a `deleted-<number>` name
  (issue #220).
<!-- release notes -->
- **A new account with the name of a deleted one now starts empty.** The old ratings and listens
  stay in the totals under `deleted-<id>`.
