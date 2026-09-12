/**
 * The two calls behind a personalized feed, and what happens when either of them lets go.
 *
 * The order is the product -- a quota per genre, a cap per artist, release date descending -- so
 * the one thing this must never do is re-sort or re-match what comes back. The rest is about
 * failing to an empty list rather than to a broken screen: an empty feed and an unreachable
 * server look the same to the caller on purpose, because both mean there is nothing to show.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import { DAILY_MIX, RELEASE_RADAR, loadFeed } from "../../src/lib/feeds.js";

vi.mock("../../src/lib/mumaApi.js", () => ({
  apiBase: () => "http://muma",
  fetchMumaJson: (...args) => globalThis.__fetchMumaJson(...args),
  // `restUrl` normally builds on `credentials.url`; a bare passthrough is enough here since
  // these tests only care that the Subsonic path and body reach `fetch` untouched.
  restUrl: (pathAndQuery) => pathAndQuery,
}));

const AUTH = "u=user&p=secret&v=1.16.1&c=test&f=json";

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
    );
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
