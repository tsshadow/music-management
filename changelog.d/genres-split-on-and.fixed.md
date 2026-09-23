- **Genres went through the artist splitter, so 'Drum & Bass' became 'Drum' and 'Bass'.**
  `CleanTagsRule` and `ResolveGenreRule` both ran `ARTIST_REGEX` over the genre tag, which splits on
  ` & `, ` and `, ` x `, ` with `, `: `, ` vs ` and ` et `. A curated genre with any of those in its
  name could never match its own row, 'Hardcore: Uptempo' became two genres, and a YouTube category
  such as 'Film & Animation' dodged its blacklist entry. Genres are now split on ';' and '/' only.
  The unused `MergeDrumAndBassGenresRule` (meant to repair exactly this, wired to nothing and calling
  a method that does not exist) and `InferGenreFromTitleRule` (no callers) are gone. Files tagged
  before this keep the halves on disk. Bug report 045.

<!-- release notes -->
- Genres such as "Drum & Bass" and "Hardcore: Uptempo" are no longer cut in two by the tagger.
