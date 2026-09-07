# Test fixtures

This directory contains small, royalty-free test fixtures used by contract and
end-to-end tests (see `docs/testing-inventory.md` and the test plan, Task 4 / Phase 7).

## `music/ci-test-track-001.mp3`

- A generated 5-second 440Hz sine tone (no commercial audio), created with:
  ```bash
  ffmpeg -f lavfi -i "sine=frequency=440:duration=5" -ar 44100 -ac 2 \
    -codec:a libmp3lame -q:a 4 tests/fixtures/music/ci-test-track-001.mp3
  ```
- Tagged with fixed ID3v2.3 metadata (title, artist, album, genre, year) plus a
  custom `TXXX:MUSIC_MANAGEMENT_ID` frame, so it can be located by a stable ID
  regardless of how each service maps its own internal identifiers.
- The expected values are documented as a schema/data file in
  `expected/ci-test-track-001.json`, not as a literal API response snapshot —
  contract and e2e tests should assert against these fields individually so an
  unrelated extra property in a response never breaks the test (see plan 4.2).

## `music/ci-test-ep-001.mp3`

- The same generated tone, retagged as a label release: title `Gabber Cowboy`, one
  artist tag holding two names (`Lil Texas & Albino`), album and year, and
  deliberately **no genre and no publisher**.
- What it is for: `tests/bdd/features/label_import.feature` places it at
  `<eps root>/Texcore/TEX001 - Lil_Texas_and_Albino_-_Gabber_Cowboy-WEB-2026-SRG/`
  with a scene NFO beside it. Everything the label chain should add — the label, the
  catalogue number, the split artists, the display artist, the genres — is therefore
  absent from the file itself, so a field turning up in the library proves a rule ran
  rather than a tag being copied across.
- Expected values in `expected/ci-test-ep-001.json`, including what the chain should
  make of it after tagging.

## Regenerating or adding fixtures

Use the same approach for any additional fixture: short (a few seconds),
generated tone or silence, predictable metadata, and a matching
`expected/<name>.json` file describing what a correct import/scan/lookup
should produce.
