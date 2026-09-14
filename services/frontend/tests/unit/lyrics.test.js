import { describe, it, expect, vi } from "vitest";
import { fetchLyricsLines } from "../../src/lib/lyrics.js";

/**
 * `subsonicJson` is not mocked here, only its `fetchImpl` -- these tests care
 * that `fetchLyricsLines` reads the same `lyricsList.structuredLyrics` shape
 * `TrackList.svelte` parses, and that anything short of a full match resolves
 * to an empty array rather than throwing.
 */
function fetchImplReturning(body) {
  return vi.fn(async () => ({ ok: true, json: async () => body }));
}

describe("fetchLyricsLines", () => {
  it("flattens the structured lyrics LMS answers with", async () => {
    const fetchImpl = fetchImplReturning({
      "subsonic-response": {
        status: "ok",
        lyricsList: {
          structuredLyrics: {
            lang: "eng",
            line: [{ value: "Raise your fist" }, { value: "in the air" }],
          },
        },
      },
    });

    const lines = await fetchLyricsLines("song-1", { fetchImpl });

    expect(lines).toEqual(["Raise your fist", "in the air"]);
  });

  it("wraps a single lyrics line the same as several", async () => {
    const fetchImpl = fetchImplReturning({
      "subsonic-response": {
        lyricsList: { structuredLyrics: { line: { value: "One line only" } } },
      },
    });

    const lines = await fetchLyricsLines("song-1", { fetchImpl });

    expect(lines).toEqual(["One line only"]);
  });

  it("resolves to an empty array when LMS has no lyrics for the track", async () => {
    const fetchImpl = fetchImplReturning({
      "subsonic-response": { status: "ok", lyricsList: { structuredLyrics: [] } },
    });

    const lines = await fetchLyricsLines("song-1", { fetchImpl });

    expect(lines).toEqual([]);
  });

  it("never calls the server for a track with no id", async () => {
    const fetchImpl = vi.fn();

    const lines = await fetchLyricsLines(null, { fetchImpl });

    expect(lines).toEqual([]);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("resolves to an empty array rather than throwing on a network failure", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("network down");
    });

    const lines = await fetchLyricsLines("song-1", { fetchImpl });

    expect(lines).toEqual([]);
  });
});
