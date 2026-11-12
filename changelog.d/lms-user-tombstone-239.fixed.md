- **A new account with the name of a deleted one got the old player data back.** The music server
  only disabled the deleted account's user and then found it by name, so a new account with that
  name took over its ratings, stars, listens and playlists. The user sync now renames that user to
  `deleted-<id>`, the same name music-manager gives the history, before it looks up new accounts,
  and never takes over a user linked to another account by name. Users of accounts deleted
  earlier are renamed on the first sync (issue #239).
<!-- release notes -->
- **A new account with the name of a deleted one now starts empty in the player too.**
