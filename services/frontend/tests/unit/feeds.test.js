/**
 * The two calls behind a personalized feed, and what happens when either of them lets go.
 *
 * The order is the product -- a quota per genre, a cap per artist, release date descending -- so
 * the one thing this must never do is re-sort or re-match what comes back. The rest is about
 * failing to an empty list rather than to a broken screen: an empty feed and an unreachable
 * server look the same to the caller on purpose, because both mean there is nothing to show.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  DAILY_MIX,
  DAILY_MIX_ARTIST,
  DAILY_MIX_HARD,
  DAILY_MIX_LABEL,
  DAILY_MIX_MID,
  DAILY_MIX_SOFT,
  DAILY_MIXES,
  OLD_HITS,
  RELEASE_RADAR,
  SHELF_FEEDS,
  feedPaths,
  fetchFeed,
  listFeeds,
  loadFeed,
  loadFeedDetail,
  loadFeedPage,
  resetFeedsCache,
  resolveFeedChunk,
  streamFeedDetail,
  SONGS_BY_PATH_LIMIT,
} from "../../src/lib/feeds.js";

vi.mock("../../src/lib/mumaApi.js", () => ({
  apiBase: () => "http://muma",
  fetchMumaJson: (...args) => globalThis.__fetchMumaJson(...args),
  // A stand-in for the store-backed real one: fixed so a test can assert the feed request
  // carries it, the way `/api/curation/*` and `/api/rules/genres` already do.
  getHeaders: () => ({ "X-API-Key": "the-users-key" }),
  // `restUrl` normally builds on `credentials.url`; a bare passthrough is enough here since
  // these tests only care that the Subsonic path and body reach `fetch` untouched.
  restUrl: (pathAndQuery) => pathAndQuery,
}));

const AUTH = "u=demo-user&p=secret&v=1.16.1&c=test&f=json";

function feedOf(...paths) {
  return {
    slug: RELEASE_RADAR,
    state: "ok",
    tracks: paths.map((path) => ({
      title: path,
      library_path: path,
      file_path: `/mnt/music/${path}`,
    })),
  };
}

function songsResponse(...ids) {
  return {
    ok: true,
    json: async () => ({
      "subsonic-response": { songsByPath: { song: ids.map((id) => ({ id })) } },
    }),
  };
}

describe("loadFeed", () => {
  beforeEach(() => {
    globalThis.__fetchMumaJson = vi.fn();
    globalThis.fetch = vi.fn();
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("resolves the feed's library paths to songs", async () => {
    globalThis.__fetchMumaJson.mockResolvedValue(feedOf("EPs/Label/01.mp3", "EPs/Label/02.mp3"));
    globalThis.fetch.mockResolvedValue(songsResponse("7", "8"));

    const tracks = await loadFeed(RELEASE_RADAR, AUTH);

    expect(tracks.map((t) => t.id)).toEqual(["7", "8"]);

    const [url, options] = globalThis.fetch.mock.calls[0];
    expect(url).toContain("/rest/getSongsByPath.view");
    expect(options.method).toBe("POST");
    expect(options.body.getAll("path")).toEqual(["EPs/Label/01.mp3", "EPs/Label/02.mp3"]);
  });

  it("asks MuMa for the feed it was given", async () => {
    globalThis.__fetchMumaJson.mockResolvedValue(feedOf("a.mp3"));
    globalThis.fetch.mockResolvedValue(songsResponse("1"));

    await loadFeed(DAILY_MIX, AUTH, 10);

    expect(globalThis.__fetchMumaJson).toHaveBeenCalledWith(
      "http://muma/api/feeds/daily-mix?limit=10",
      { headers: { "X-API-Key": "the-users-key" } },
    );
  });

  it("carries the user's own key, like every other /api call -- this is a per-user feed", async () => {
    globalThis.__fetchMumaJson.mockResolvedValue(feedOf("a.mp3"));
    globalThis.fetch.mockResolvedValue(songsResponse("1"));

    await loadFeed(RELEASE_RADAR, AUTH);

    const [, options] = globalThis.__fetchMumaJson.mock.calls[0];
    expect(options.headers).toEqual({ "X-API-Key": "the-users-key" });
  });

  it("keeps the server's order rather than sorting it again", async () => {
    globalThis.__fetchMumaJson.mockResolvedValue(feedOf("a.mp3", "b.mp3", "c.mp3"));
    globalThis.fetch.mockResolvedValue(songsResponse("3", "1", "2"));

    const tracks = await loadFeed(RELEASE_RADAR, AUTH);

    expect(tracks.map((t) => t.id)).toEqual(["3", "1", "2"]);
  });

  it("sends the absolute path nowhere -- LMS does not have that spelling", async () => {
    globalThis.__fetchMumaJson.mockResolvedValue(feedOf("EPs/x/01.mp3"));
    globalThis.fetch.mockResolvedValue(songsResponse("1"));

    await loadFeed(RELEASE_RADAR, AUTH);

    expect(globalThis.fetch.mock.calls[0][1].body.getAll("path")).toEqual(["EPs/x/01.mp3"]);
  });

  it("never asks LMS to resolve nothing", async () => {
    globalThis.__fetchMumaJson.mockResolvedValue({
      slug: RELEASE_RADAR,
      state: "not_enough_data",
      tracks: [],
    });

    expect(await loadFeed(RELEASE_RADAR, AUTH)).toEqual([]);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("is empty when MuMa cannot be reached", async () => {
    globalThis.__fetchMumaJson.mockRejectedValue(new Error("gate refused"));

    expect(await loadFeed(RELEASE_RADAR, AUTH)).toEqual([]);
  });

  it("is empty when the songs cannot be resolved", async () => {
    globalThis.__fetchMumaJson.mockResolvedValue(feedOf("a.mp3"));
    globalThis.fetch.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });

    expect(await loadFeed(RELEASE_RADAR, AUTH)).toEqual([]);
  });

  it("survives a single song coming back unwrapped", async () => {
    // Subsonic's JSON collapses a one-element array into the object itself, which has broken
    // every list in this app at least once.
    globalThis.__fetchMumaJson.mockResolvedValue(feedOf("a.mp3"));
    globalThis.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ "subsonic-response": { songsByPath: { song: { id: "1" } } } }),
    });

    expect((await loadFeed(RELEASE_RADAR, AUTH)).map((t) => t.id)).toEqual(["1"]);
  });

  it("does nothing at all without credentials", async () => {
    expect(await loadFeed(RELEASE_RADAR, "")).toEqual([]);
    expect(globalThis.__fetchMumaJson).not.toHaveBeenCalled();
  });

  it("drops a feed entry that carries no library path", async () => {
    globalThis.__fetchMumaJson.mockResolvedValue({
      slug: RELEASE_RADAR,
      state: "ok",
      tracks: [{ title: "no path" }, { title: "ok", library_path: "a.mp3" }],
    });
    globalThis.fetch.mockResolvedValue(songsResponse("1"));

    await loadFeed(RELEASE_RADAR, AUTH);

    expect(globalThis.fetch.mock.calls[0][1].body.getAll("path")).toEqual(["a.mp3"]);
  });
});

describe("the five daily mixes are real slugs", () => {
  it("lists soft, mid, hard, artist and label, and never the classic mix", () => {
    expect(DAILY_MIXES).toEqual([
      DAILY_MIX_SOFT,
      DAILY_MIX_MID,
      DAILY_MIX_HARD,
      DAILY_MIX_ARTIST,
      DAILY_MIX_LABEL,
    ]);
    expect(DAILY_MIXES).not.toContain(DAILY_MIX);
  });

  it("puts Oude hitjes on the shelf after the mixes, without making it a daily mix", () => {
    expect(SHELF_FEEDS).toEqual([...DAILY_MIXES, OLD_HITS]);
    expect(DAILY_MIXES).not.toContain(OLD_HITS);
  });
});

describe("listFeeds", () => {
  afterEach(() => resetFeedsCache());

  it("asks MuMa for every feed, with the user's key", async () => {
    globalThis.__fetchMumaJson.mockResolvedValue({
      feeds: [{ slug: DAILY_MIX, title: "Klassiek", subtitle: null }],
    });

    const feeds = await listFeeds();

    expect(feeds).toEqual([{ slug: DAILY_MIX, title: "Klassiek", subtitle: null }]);
    expect(globalThis.__fetchMumaJson).toHaveBeenCalledWith("http://muma/api/feeds", {
      headers: { "X-API-Key": "the-users-key" },
    });
  });

  it("asks only once per session -- a second call reuses the first answer", async () => {
    globalThis.__fetchMumaJson.mockResolvedValue({ feeds: [] });

    await listFeeds();
    await listFeeds();

    expect(globalThis.__fetchMumaJson).toHaveBeenCalledTimes(1);
  });

  it("is an empty list rather than a crash when MuMa is unreachable", async () => {
    globalThis.__fetchMumaJson.mockRejectedValue(new Error("gate refused"));

    expect(await listFeeds()).toEqual([]);
  });

  it("does not cache an answer without a feed list -- an error body is not 'no feeds'", async () => {
    globalThis.__fetchMumaJson.mockResolvedValueOnce({ detail: "Not authenticated" });
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(await listFeeds()).toEqual([]);

    globalThis.__fetchMumaJson.mockResolvedValue({ feeds: [{ slug: DAILY_MIX }] });
    expect(await listFeeds()).toEqual([{ slug: DAILY_MIX }]);
    expect(globalThis.__fetchMumaJson).toHaveBeenCalledTimes(2);
  });

  it("retries the next time after a failure -- the cache does not remember an error", async () => {
    globalThis.__fetchMumaJson.mockRejectedValueOnce(new Error("gate refused"));
    await listFeeds();

    globalThis.__fetchMumaJson.mockResolvedValue({ feeds: [{ slug: DAILY_MIX }] });
    expect(await listFeeds()).toEqual([{ slug: DAILY_MIX }]);
  });
});

describe("fetchFeed", () => {
  it("carries the title, subtitle and hardness fields through untouched", async () => {
    globalThis.__fetchMumaJson.mockResolvedValue({
      slug: DAILY_MIX_SOFT,
      state: "ok",
      tracks: [],
      title: "Zachter",
      subtitle: "≤ 42 hardheid",
      hardness_band: [10, 42],
      relaxed_to: "none",
      filled_from_unknown: 3,
    });

    const feed = await fetchFeed(DAILY_MIX_SOFT, 10);

    expect(feed.title).toBe("Zachter");
    expect(feed.hardness_band).toEqual([10, 42]);
    expect(feed.filled_from_unknown).toBe(3);
  });

  it("answers a safe, empty shape when MuMa cannot be reached", async () => {
    globalThis.__fetchMumaJson.mockRejectedValue(new Error("gate refused"));

    const feed = await fetchFeed(DAILY_MIX_SOFT);

    expect(feed).toEqual({
      slug: DAILY_MIX_SOFT,
      state: "error",
      tracks: [],
      title: null,
      subtitle: null,
      hardness_band: null,
      relaxed_to: null,
      filled_from_unknown: null,
    });
  });
});

describe("feedPaths", () => {
  it("works for any slug, not only the original two", async () => {
    globalThis.__fetchMumaJson.mockResolvedValue({
      slug: DAILY_MIX_LABEL,
      state: "ok",
      tracks: [{ library_path: "EPs/Label/01.mp3" }],
    });

    const paths = await feedPaths(DAILY_MIX_LABEL, 5);

    expect(paths).toEqual(["EPs/Label/01.mp3"]);
    expect(globalThis.__fetchMumaJson).toHaveBeenCalledWith(
      "http://muma/api/feeds/daily-mix-label?limit=5",
      { headers: { "X-API-Key": "the-users-key" } },
    );
  });
});

describe("loadFeedDetail", () => {
  it("resolves the feed's own tracks and carries the server's title/subtitle", async () => {
    globalThis.__fetchMumaJson.mockResolvedValue({
      slug: DAILY_MIX_MID,
      state: "ok",
      tracks: [{ library_path: "a.mp3" }],
      title: "Middenin",
      subtitle: "42–70 hardheid",
      hardness_band: [42, 70],
      relaxed_to: null,
      filled_from_unknown: 0,
    });
    globalThis.fetch.mockResolvedValue(songsResponse("1"));

    const detail = await loadFeedDetail(DAILY_MIX_MID, AUTH);

    expect(detail.title).toBe("Middenin");
    expect(detail.subtitle).toBe("42–70 hardheid");
    expect(detail.hardnessBand).toEqual([42, 70]);
    expect(detail.filledFromUnknown).toBe(0);
    expect(detail.tracks.map((t) => t.id)).toEqual(["1"]);
  });

  it("carries a null hardness band for a feed that never sets one", async () => {
    globalThis.__fetchMumaJson.mockResolvedValue(feedOf("a.mp3"));
    globalThis.fetch.mockResolvedValue(songsResponse("1"));

    const detail = await loadFeedDetail(RELEASE_RADAR, AUTH);

    expect(detail.hardnessBand).toBeNull();
    expect(detail.filledFromUnknown).toBeNull();
  });

  it("has no tracks to resolve without credentials", async () => {
    globalThis.__fetchMumaJson.mockResolvedValue(feedOf("a.mp3"));

    const detail = await loadFeedDetail(RELEASE_RADAR, "");

    expect(detail.tracks).toEqual([]);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

describe("feed pages (docs/designs/feed-length/)", () => {
  beforeEach(() => {
    globalThis.__fetchMumaJson = vi.fn();
    globalThis.fetch = vi.fn();
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("asks for a page with an offset, and for the head without one", async () => {
    globalThis.__fetchMumaJson.mockResolvedValue(feedOf());

    await fetchFeed(DAILY_MIX, undefined, 100);
    await fetchFeed(DAILY_MIX, 10);
    await fetchFeed(DAILY_MIX);

    const urls = globalThis.__fetchMumaJson.mock.calls.map(([url]) => url);
    expect(urls).toEqual([
      "http://muma/api/feeds/daily-mix?offset=100",
      "http://muma/api/feeds/daily-mix?limit=10",
      "http://muma/api/feeds/daily-mix",
    ]);
  });

  it("carries where the feed continues, and null when it does not", async () => {
    globalThis.__fetchMumaJson.mockResolvedValueOnce({ ...feedOf("a.mp3"), next_offset: 100 });
    globalThis.__fetchMumaJson.mockResolvedValueOnce({ ...feedOf("a.mp3"), next_offset: null });
    globalThis.fetch.mockResolvedValue(songsResponse("1"));

    expect((await loadFeedDetail(DAILY_MIX, AUTH)).nextOffset).toBe(100);
    expect((await loadFeedDetail(DAILY_MIX, AUTH)).nextOffset).toBeNull();
  });

  it("loads the next page as songs, with the offset after it", async () => {
    globalThis.__fetchMumaJson.mockResolvedValue({ ...feedOf("b.mp3", "c.mp3"), next_offset: 200 });
    globalThis.fetch.mockResolvedValue(songsResponse("2", "3"));

    const page = await loadFeedPage(DAILY_MIX, AUTH, 100);

    expect(page).toEqual({
      tracks: [{ id: "2" }, { id: "3" }],
      nextOffset: 200,
      unresolved: 0,
      failed: false,
    });
    expect(globalThis.__fetchMumaJson.mock.calls[0][0]).toContain("offset=100");
  });

  it("says a page failed rather than that the feed ended", async () => {
    globalThis.__fetchMumaJson.mockRejectedValue(new Error("down"));

    const page = await loadFeedPage(DAILY_MIX, AUTH, 100);

    expect(page).toEqual({ tracks: [], nextOffset: 100, unresolved: 0, failed: true });
  });

  it("resolves a feed longer than LMS accepts in one call in chunks, in order", async () => {
    const paths = Array.from({ length: 150 }, (_, i) => `t${i}.mp3`);
    globalThis.__fetchMumaJson.mockResolvedValue(feedOf(...paths));
    globalThis.fetch
      .mockResolvedValueOnce(songsResponse(...paths.slice(0, 100)))
      .mockResolvedValueOnce(songsResponse(...paths.slice(100)));

    const detail = await loadFeedDetail(DAILY_MIX, AUTH);

    expect(SONGS_BY_PATH_LIMIT).toBe(100);
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
    const sent = globalThis.fetch.mock.calls.map(([, options]) => options.body.getAll("path"));
    expect(sent.map((chunk) => chunk.length)).toEqual([100, 50]);
    expect(detail.tracks.map((t) => t.id)).toEqual(paths);
  });

  // Bug report 122: Harder showed 98 of MuMa's 100 because two paths had no song in LMS.
  it("counts the paths LMS had no song for, and pages by MuMa's rows regardless", async () => {
    const paths = Array.from({ length: 100 }, (_, i) => `t${i}.mp3`);
    globalThis.__fetchMumaJson.mockResolvedValue({ ...feedOf(...paths), next_offset: 100 });
    globalThis.fetch.mockResolvedValue(songsResponse(...paths.slice(0, 98)));

    const detail = await loadFeedDetail(DAILY_MIX_HARD, AUTH);

    expect(detail.tracks).toHaveLength(98);
    expect(detail.unresolved).toBe(2);
    expect(detail.nextOffset).toBe(100);
  });

  it("counts a later page's unresolved paths too", async () => {
    globalThis.__fetchMumaJson.mockResolvedValue({
      ...feedOf("a.mp3", "b.mp3", "c.mp3"),
      next_offset: 200,
    });
    globalThis.fetch.mockResolvedValue(songsResponse("a.mp3"));

    const page = await loadFeedPage(DAILY_MIX_HARD, AUTH, 100);

    expect(page.unresolved).toBe(2);
    expect(page.nextOffset).toBe(200);
  });
});

/** Issue #110: the chunks are asked for at once and reported as they land. */
describe("streamFeedDetail", () => {
  beforeEach(() => {
    globalThis.__fetchMumaJson = vi.fn();
    globalThis.fetch = vi.fn();
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => vi.restoreAllMocks());

  it("asks LMS for every chunk before the first has answered", async () => {
    const paths = Array.from({ length: 150 }, (_, i) => `t${i}.mp3`);
    globalThis.__fetchMumaJson.mockResolvedValue(feedOf(...paths));
    const answers = [];
    globalThis.fetch.mockImplementation(() => new Promise((resolve) => answers.push(resolve)));

    const done = streamFeedDetail(DAILY_MIX, AUTH);
    await vi.waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(2));

    // Answered in reverse: the result still follows MuMa's order.
    answers[1](songsResponse(...paths.slice(100)));
    answers[0](songsResponse(...paths.slice(0, 100)));
    const detail = await done;
    expect(detail.tracks.map((t) => t.id)).toEqual(paths);
  });

  it("reports the header before any song, then each chunk by its index", async () => {
    const paths = Array.from({ length: 101 }, (_, i) => `t${i}.mp3`);
    globalThis.__fetchMumaJson.mockResolvedValue({ ...feedOf(...paths), title: "Harder" });
    globalThis.fetch
      .mockResolvedValueOnce(songsResponse(...paths.slice(0, 100)))
      .mockResolvedValueOnce(songsResponse(...paths.slice(100)));
    const events = [];

    await streamFeedDetail(DAILY_MIX_HARD, AUTH, {
      onHeader: (header) =>
        events.push(["header", header.title, header.chunks.map((c) => c.length)]),
      onChunk: (index, result) => events.push(["chunk", index, result.songs.length]),
    });

    expect(events[0]).toEqual(["header", "Harder", [100, 1]]);
    expect(events.slice(1).sort()).toEqual([
      ["chunk", 0, 100],
      ["chunk", 1, 1],
    ]);
  });

  it("counts a chunk LMS failed to answer as failed, not as unresolved paths", async () => {
    const paths = Array.from({ length: 150 }, (_, i) => `t${i}.mp3`);
    globalThis.__fetchMumaJson.mockResolvedValue(feedOf(...paths));
    globalThis.fetch
      .mockResolvedValueOnce(songsResponse(...paths.slice(0, 99)))
      .mockResolvedValueOnce({ ok: false, status: 503 });

    const detail = await streamFeedDetail(DAILY_MIX, AUTH);

    expect(detail.failedChunks).toBe(1);
    expect(detail.unresolved).toBe(1);
    expect(detail.tracks).toHaveLength(99);
  });

  it("resolves one chunk again for a retry", async () => {
    globalThis.fetch.mockResolvedValue(songsResponse("a.mp3"));

    expect(await resolveFeedChunk(["a.mp3"], AUTH)).toEqual({
      songs: [{ id: "a.mp3" }],
      failed: false,
    });
  });

  it("treats a next page whose chunk failed as a failed page, keeping the continuation", async () => {
    globalThis.__fetchMumaJson.mockResolvedValue({ ...feedOf("a.mp3"), next_offset: 200 });
    globalThis.fetch.mockResolvedValue({ ok: false, status: 503 });

    const page = await loadFeedPage(DAILY_MIX, AUTH, 100);

    expect(page).toEqual({ tracks: [], nextOffset: 100, unresolved: 0, failed: true });
  });
});
