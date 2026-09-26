- **Confirming a label proposal, renaming a podcast show, changing an artist's portrait, revoking a
  user's sessions and grouping song versions could stop half-way.** The music-manager database pool
  commits every statement on its own, and each of these wrote two or more statements in a row. A
  failure in between could leave a CAT-ID rule in force behind a proposal that still read as open, a
  renamed show whose old spelling was lost for good, a portrait flagged in the manager that the
  artist did not actually show, an api_key cleared while its refresh tokens stayed valid, or grouped
  song versions without a canonical that no later pass would ever repair. Each now runs in one
  transaction: all of it lands, or none of it does (bug report 115).
<!-- release notes -->
- Confirming a label, renaming a podcast, changing an artist's picture, signing a user out
  everywhere and grouping song versions can no longer leave half-done data behind when something
  fails midway.
