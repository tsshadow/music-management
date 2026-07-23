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

## Regenerating or adding fixtures

Use the same approach for any additional fixture: short (a few seconds),
generated tone or silence, predictable metadata, and a matching
`expected/<name>.json` file describing what a correct import/scan/lookup
should produce.
