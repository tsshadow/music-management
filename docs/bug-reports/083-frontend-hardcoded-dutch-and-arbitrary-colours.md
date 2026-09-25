# Web frontend: hard-coded Dutch text, fixed 'nl-NL' formatting, arbitrary colours, doubled search fetch

# status: fixed

# reported problem

Audit finding C14 (2026-09-23), for `services/frontend`:

- Interface text typed straight into components in Dutch: error messages, `confirm()`/`alert()`
  dialogs, titles and headings, and the media-session fallback "Onbekend nummer" that the lock
  screen and a car head unit show. A user who chose English still got these in Dutch.
- `toLocaleString('nl-NL')` / `toLocaleDateString('nl-NL')` hard-coded in about a dozen files, so
  an English interface grouped digits as `1.234` and wrote dates the Dutch way.
- About 860 arbitrary colour classes (`text-[#b3b3b3]` alone ~440 times) instead of the design
  tokens in `src/app.css`, several of them for colours the styleguide already names.
- `hover:bg-opacity-80` in `GenreEdit.svelte`: Tailwind v3 syntax that compiles to nothing in v4,
  so the button had no hover state.
- `TopBar.svelte` renders two `SearchBar`s (phone and desktop), each fetching the full genre and
  record-label lists on mount.

# Possible reason

The i18n module arrived after most management and curation screens were written, and nothing
checked for new hard-coded text afterwards. The colour tokens were declared for only five of the
greys in use, so copying a neighbouring component's `-[#hex]` was the path of least resistance.
The Tailwind v4 upgrade silently dropped `bg-opacity-*`. The two search bars sit in the two
branches of an `{#if $isMobile}` -- only one is mounted at a time, but crossing the breakpoint
(rotating a tablet, resizing the window) unmounts one and mounts the other, and every mount
fetched both lists again.

# solution

- Every user-visible Dutch string in components and the label-returning helper modules moved to
  `src/lib/i18n/locales/en.json` / `nl.json` (the Dutch text verbatim) and is read through `$t`
  (`get(t)` in plain modules). Native `confirm()` stays -- the app has no confirm-dialog
  component -- but with translated text; the one `alert()` became `notify.warning`. The media
  session falls back to `player.unknownTrack` / `unknownArtist` / `unknownAlbum`. Messages that
  only reach the console stay as they were.
- `src/lib/i18n/index.js` gained `formatNumber`, `formatDate`, `formatDateTime` and a `format`
  store bound to the active locale (dialects format as Dutch); all `'nl-NL'` calls use them.
- `tests/unit/noHardcodedDutch.test.js` scans `src/` (comments and `console.*` lines excluded)
  for the moved phrases and for `nl-NL`; `tests/unit/i18nFormat.test.js` covers the formatters.
- Five tokens added to `@theme` -- `muma-spotify-muted` (#727272), `-subtle` (#535353), `-raised`
  (#242424), `-hover` (#333333), `-highlight` (#3e3e3e) -- and every arbitrary class whose hex maps
  1:1 onto a token (including the existing `-dark`, `-panel`, `-light`, `-text`, `brand-green`)
  rewritten by script, in components and in the tests that assert class names. Same hex, so no
  pixel changes. The ~40 remaining arbitrary colours have no token and are listed in
  `docs/styleguide.md`.
- `GenreEdit.svelte` uses `hover:bg-muma-spotify-light/80`; no other `*-opacity-*` utilities exist.
- `src/lib/searchFacets.js` loads genres and labels once and shares the in-flight request and its
  result between every `SearchBar`; a failed list is not cached, so the next mount retries.
