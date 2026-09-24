# Genres Were Cut In Two On '&', 'and' And ': ' By The Artist Splitter

# status: fixed — the genre tag is split on ';' and '/' only; the dead repair rule is deleted

# reported problem
A review of the tagger's genre path found that a genre tag never reaches curation as written when
its name contains an artist separator:

- `Drum & Bass` is stored as two genres, `Drum` and `Bass`;
- `Hardcore: Uptempo` becomes `Hardcore` and `Uptempo`;
- a curated genre with `&`, ` and ` or `: ` in its name can never match its own `rules_genres` row,
  because by the time `ResolveGenreRule` looks it up it is two strings;
- the YouTube category names `migrate_v7_youtube_category_genres.sql` blacklists (`Film & Animation`,
  `News & Politics`, ...) only ever matched through the halves that migration had to list as well,
  and those halves (`News`, `Style`, `Events`, ...) are blacklisted for every source.

# Possible reason
`Tag.regex()` is the artist splitter: it replaces every match of `ARTIST_REGEX` with ';' and
re-splits. `ARTIST_REGEX` matches ` & `, ` and `, ` x `, ` with `, `: `, ` vs `, ` et `, `, `,
`feat.` and more — right for `Angerfist & Miss K8`, wrong for a genre. Two rules ran it over
`GENRE`:

- `CleanTagsRule` listed `GENRE` next to `ARTIST`, `ALBUM_ARTIST` and `REMIXER`, and runs twice in
  every song type's rule chain;
- `ResolveGenreRule` called `genre_tag.regex()` before resolving, so even a genre that survived the
  first rule was split right before the lookup.

`MergeDrumAndBassGenresRule` was written to glue `Drum` and `Bass` back together. It is registered
in no song type, and it calls `Tag.as_list()`, which does not exist — its test passed only because
it mocked the tag. `InferGenreFromTitleRule` is likewise registered nowhere.

The rule tests on both sides mock the `Tag`, so they asserted that `regex()` was called and never
what it did to a genre.

# solution
- `CleanTagsRule` runs `Tag.regex()` over `ARTIST`, `ALBUM_ARTIST` and `REMIXER` only (`ARTIST_FIELDS`);
  `GENRE` is still stripped and deduplicated there.
- `ResolveGenreRule` no longer calls `Tag.regex()`. A genre is split on ';' by `Tag` itself and on '/'
  by `GenreRulesHelper.split_composite`, which leaves a decided genre whole — that is the whole genre
  splitter.
- `MergeDrumAndBassGenresRule` and its test are deleted rather than fixed and wired: with the split
  gone there is nothing left for it to repair, and wiring it would have hard-coded one genre's
  spelling (`drum 'n bass`) past the curation model, where a spelling is a curator's decision
  (a black row with an expansion). `InferGenreFromTitleRule` and its test are deleted too: no song
  type uses it, and its dry-run mode opened a file in its constructor.
- `services/tagger/Song/rules/GenrePathTest.py` runs `CleanTagsRule` twice and `ResolveGenreRule`
  over a real `TagCollection` read from an mp3 tag dict: `Drum & Bass` survives and resolves against
  a rules table containing it, `Film & Animation` meets its blacklist row, ';' and '/' still separate.
- `docs/designs/tagger/technical.md` (Genre Splitting) and `docs/designs/genre-curation/technical.md`
  describe the rule.

Not repaired: files the tagger already wrote carry the halves on disk (`Drum;Bass`), and the
original string is gone, so the tagger cannot restore it. Those need their genre corrected by hand
or a re-download; the unknown `Drum`/`Bass` rows in the curation queue can be rejected or expanded
to `Drum & Bass` as usual. The halves `migrate_v7` blacklists stay: they still match those old files.
