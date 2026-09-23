- **Any account could start a ListenBrainz import into any other account's history.**
  `POST /api/scrobble/import/listenbrainz` took `username` from the body without checking it against
  the caller. An ordinary account may now only import into its own history (403 otherwise); admins
  and the system key may still name anyone.
