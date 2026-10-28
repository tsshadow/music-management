/**
 * The paged track sources a list page and a playing queue share (docs/designs/list-continuation/).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

import {
  fetchHistoryPage,
  fetchSpotifyTracksPage,
  getSongsContinuation,
  hasMoreResults,
  historyContinuation,
  spotifyTracksContinuation,
} from "../../src/lib/trackPages.js";
import { credentials } from "../../src/lib/store.js";

/** A `getSpotifyTracks` stand-in answering `pages[offset]`. */
function spotifyTracks(pages) {
  return vi.fn(async (_method, params) => {
    const page = pages[params.offset] ?? { track: [], moreResults: false };
    return { "subsonic-response": { status: "ok", tracks: page } };
  });
}

const ids = (list) => list.map((t) => ({ id: t }));

describe("hasMoreResults", () => {
  it("reads LMS's boolean or string, and falls back to a full page", () => {
    expect(hasMoreResults(true, 1, 50)).toBe(true);
    expect(hasMoreResults("true", 1, 50)).toBe(true);
    expect(hasMoreResults("false", 50, 50)).toBe(false);
    expect(hasMoreResults(undefined, 50, 50)).toBe(true);
    expect(hasMoreResults(undefined, 49, 50)).toBe(false);
  });
});

describe("fetchSpotifyTracksPage", () => {
  it("fills a page across calls and follows nextOffset", async () => {
    const fetchJson = spotifyTracks({
      0: { track: ids(["a"]), moreResults: true, nextOffset: 5 },
      5: { track: ids(["b", "c"]), moreResults: true, nextOffset: 9 },
    });

    const page = await fetchSpotifyTracksPage({ sort: "recent" }, 0, { pageSize: 3, fetchJson });

    expect(page).toEqual({ tracks: ids(["a", "b", "c"]), nextOffset: 9, hasMore: true });
    expect(fetchJson.mock.calls[1][1]).toMatchObject({ sort: "recent", offset: 5, count: 3 });
  });

  it("folds versions of one song together against what was seen before", async () => {
    const fetchJson = spotifyTracks({
      0: {
        track: [
          { id: "a", workId: 7 },
          { id: "b", workId: 8 },
        ],
        moreResults: false,
        nextOffset: 2,
      },
    });
    const seen = new Map([["work:7", { id: "older" }]]);

    const page = await fetchSpotifyTracksPage({}, 0, { pageSize: 5, seen, fetchJson });

    expect(page.tracks.map((t) => t.id)).toEqual(["b"]);
    expect(seen.has("work:8")).toBe(true);
  });

  it("stops on an answer that claims more but makes no progress", async () => {
    const fetchJson = vi.fn(async () => ({
      "subsonic-response": { tracks: { track: [], moreResults: true, nextOffset: 0 } },
    }));

    const page = await fetchSpotifyTracksPage({}, 0, { pageSize: 5, fetchJson });

    expect(page.hasMore).toBe(false);
    expect(fetchJson).toHaveBeenCalledTimes(1);
  });
});

describe("spotifyTracksContinuation", () => {
  it("is null when the list does not continue", () => {
    expect(spotifyTracksContinuation({}, null)).toBeNull();
  });

  it("asks the list's own query from its cursor, and ends with the list", async () => {
    const fetchJson = spotifyTracks({
      2: { track: ids(["c", "d"]), moreResults: true, nextOffset: 4 },
      4: { track: ids(["e"]), moreResults: false, nextOffset: 5 },
    });
    const continuation = spotifyTracksContinuation({ sort: "recent", genre: "Hardcore" }, 2, {
      pageSize: 2,
      fetchJson,
    });

    expect(continuation.kind).toBe("songs");
    expect(await continuation.fetchNext(2, { queue: [] })).toEqual({
      tracks: ids(["c", "d"]),
      cursor: 4,
    });
    expect(await continuation.fetchNext(4, { queue: [] })).toEqual({
      tracks: ids(["e"]),
      cursor: null,
    });
    expect(fetchJson.mock.calls[0][1]).toMatchObject({ sort: "recent", genre: "Hardcore" });
  });

  it("folds versions against the queue when deduplicating", async () => {
    const fetchJson = spotifyTracks({
      2: { track: [{ id: "x", workId: 3 }, { id: "y" }], moreResults: false },
    });
    const continuation = spotifyTracksContinuation({}, 2, { pageSize: 5, dedupe: true, fetchJson });

    const page = await continuation.fetchNext(2, { queue: [{ id: "queued", workId: 3 }] });

    expect(page.tracks.map((t) => t.id)).toEqual(["y"]);
  });

  it("reports a failed page instead of throwing", async () => {
    const continuation = spotifyTracksContinuation({}, 2, {
      fetchJson: vi.fn(async () => {
        throw new Error("offline");
      }),
    });

    expect(await continuation.fetchNext(2)).toEqual({ tracks: [], cursor: 2, failed: true });
  });
});

describe("getSongsContinuation", () => {
  it("asks the same query page by page and ends on a short page", async () => {
    const fetchJson = vi.fn(async (_m, params) => ({
      "subsonic-response": { songs: { song: params.offset === 2 ? ids(["c", "d"]) : ids(["e"]) } },
    }));
    const build = vi.fn((offset, count) => ({
      method: "getSongs",
      params: { seed: 42, offset, count },
    }));
    const continuation = getSongsContinuation(build, 2, { pageSize: 2, fetchJson });

    expect(await continuation.fetchNext(2)).toEqual({ tracks: ids(["c", "d"]), cursor: 4 });
    expect(await continuation.fetchNext(4)).toEqual({ tracks: ids(["e"]), cursor: null });
    expect(build).toHaveBeenCalledWith(4, 2);
    expect(getSongsContinuation(build, null)).toBeNull();
  });

  it("reports a failed page instead of throwing", async () => {
    const continuation = getSongsContinuation(() => ({ method: "getSongs", params: {} }), 0, {
      fetchJson: vi.fn(async () => {
        throw new Error("no");
      }),
    });
    expect(await continuation.fetchNext(0)).toMatchObject({ failed: true, cursor: 0 });
  });
});

describe("history", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "demo-user", password: "pw" });
  });

  function historyFetch(pages) {
    return vi.fn(async (url) => {
      const offset = Number(new URL(url, "http://x").searchParams.get("offset"));
      const page = pages[offset];
      if (!page) return { ok: false, json: async () => ({}) };
      return { ok: true, json: async () => ({ "subsonic-response": { history: page } }) };
    });
  }

  it("reads one page of the history", async () => {
    const fetchImpl = historyFetch({ 0: { entry: { id: "a" }, moreResults: true } });

    expect(await fetchHistoryPage(0, 2, "u=demo-user", { fetchImpl })).toEqual({
      entries: ids(["a"]),
      hasMore: true,
    });
  });

  it("continues the history by offset and ends with it", async () => {
    const fetchImpl = historyFetch({
      2: { entry: ids(["c", "d"]), moreResults: true },
      4: { entry: ids(["e"]), moreResults: false },
    });
    const continuation = historyContinuation(2, { pageSize: 2, fetchImpl });

    expect(await continuation.fetchNext(2)).toEqual({ tracks: ids(["c", "d"]), cursor: 4 });
    expect(await continuation.fetchNext(4)).toEqual({ tracks: ids(["e"]), cursor: null });
    expect(await continuation.fetchNext(9)).toMatchObject({ failed: true, cursor: 9 });
    expect(historyContinuation(null)).toBeNull();
  });
});
