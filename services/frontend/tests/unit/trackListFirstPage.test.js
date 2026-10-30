/**
 * A track list's first rows arrive in the time a short answer takes (docs/designs/perceived-performance/,
 * "Small first page"): the first request asks 50 rows whatever the page size, the rest of the page
 * is fetched behind them with versions folded across both, a revisit comes from the cache whole,
 * and a request the listener left behind is aborted.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/svelte";

import Dashboard from "../../src/lib/Dashboard.svelte";
import { resetFeedsCache } from "../../src/lib/feeds.js";
import {
  FIRST_TRACK_PAGE,
  firstTrackPageSize,
  topUpTrackPage,
  trackListCache,
} from "../../src/lib/trackListCache.js";
import {
  credentials,
  deduplicateEnabled,
  favoriteGenres,
  memoriesOnHomeEnabled,
  subsonicToken,
  trackPageSize,
  viewMode,
} from "../../src/lib/store.js";

const track = (id, extra = {}) => ({
  id,
  title: `Title ${id}`,
  artist: "Track Artist",
  artistId: "ar-9",
  duration: 200,
  ...extra,
});

/** `count` tracks with ids `${prefix}0`, `${prefix}1`... */
const tracks = (prefix, count) => Array.from({ length: count }, (_, i) => track(`${prefix}${i}`));

const ok = (payload) => ({
  ok: true,
  json: async () => ({ "subsonic-response": { status: "ok", ...payload } }),
});

/** Rendering a list of 50+ rows takes a while on a loaded CI runner. */
const SLOW = { timeout: 5000 };

/** The query string of a request as a URLSearchParams. */
const query = (url) => new URLSearchParams(url.slice(url.indexOf("?") + 1));

/**
 * A fetch that holds every `getSpotifyTracks` request until the test answers it, and records the
 * signal each one travelled with. Everything else is answered at once and empty.
 */
function heldFetch() {
  const pending = [];
  const fetch = vi.fn((url, init = {}) => {
    if (!url.includes("getSpotifyTracks")) return Promise.resolve(ok({}));
    return new Promise((resolve, reject) => {
      const entry = { url, signal: init.signal, resolve, reject };
      pending.push(entry);
      init.signal?.addEventListener("abort", () => {
        const error = new Error("aborted");
        error.name = "AbortError";
        reject(error);
      });
    });
  });
  const take = (fragment) => {
    const index = pending.findIndex((entry) => entry.url.includes(fragment));
    if (index < 0) throw new Error(`no held request for ${fragment}`);
    return pending.splice(index, 1)[0];
  };
  return {
    fetch,
    pending,
    calls: () =>
      fetch.mock.calls.map(([url]) => url).filter((url) => url.includes("getSpotifyTracks")),
    take,
    answer(fragment, rows, { moreResults = false, nextOffset } = {}) {
      take(fragment).resolve(ok({ tracks: { track: rows, moreResults, nextOffset } }));
    },
  };
}

describe("firstTrackPageSize", () => {
  it("caps the first request at 50 rows and never asks more than the page holds", () => {
    expect(FIRST_TRACK_PAGE).toBe(50);
    expect(firstTrackPageSize(200)).toBe(50);
    expect(firstTrackPageSize(500)).toBe(50);
    expect(firstTrackPageSize(25)).toBe(25);
  });
});

describe("topUpTrackPage", () => {
  /** A `getSpotifyTracks` stand-in answering `pages[offset]`. */
  const answering = (pages) =>
    vi.fn(async (_method, params) => ({
      "subsonic-response": {
        status: "ok",
        tracks: pages[params.offset] ?? { track: [], moreResults: false },
      },
    }));

  it("fills the page from where it stopped, folding versions against the rows already shown", async () => {
    const first = {
      tracks: [track("a", { workId: 7 }), track("b")],
      nextOffset: 2,
      hasMore: true,
      seen: [
        ["work:7", track("a", { workId: 7 })],
        ["track:b", track("b")],
      ],
    };
    const fetchJson = answering({
      // "a2" is another version of "a": already on screen, so it must not appear twice.
      2: {
        track: [track("a2", { workId: 7 }), track("c"), track("d")],
        moreResults: true,
        nextOffset: 5,
      },
    });

    const page = await topUpTrackPage({ sort: "recent" }, first, { pageSize: 4, fetchJson });

    expect(page.tracks.map((t) => t.id)).toEqual(["a", "b", "c", "d"]);
    expect(page.nextOffset).toBe(5);
    expect(page.hasMore).toBe(true);
    expect(page.seen.map(([key]) => key)).toEqual(["work:7", "track:b", "track:c", "track:d"]);
    expect(fetchJson.mock.calls[0][1]).toMatchObject({ sort: "recent", offset: 2, count: 2 });
  });

  it("leaves the caller's version keys alone when the top-up fails halfway", async () => {
    const seen = [["track:a", track("a")]];
    const first = { tracks: [track("a")], nextOffset: 1, hasMore: true, seen };
    let calls = 0;
    const fetchJson = vi.fn(async () => {
      calls += 1;
      if (calls > 1) throw new Error("network down");
      return {
        "subsonic-response": {
          status: "ok",
          tracks: { track: [track("b")], moreResults: true, nextOffset: 2 },
        },
      };
    });

    await expect(topUpTrackPage({}, first, { pageSize: 10, fetchJson })).rejects.toThrow(
      "network down",
    );
    expect(seen).toEqual([["track:a", track("a")]]);
    expect(first.tracks.map((t) => t.id)).toEqual(["a"]);
  });

  it("asks nothing when the page is full or the list has nothing more", async () => {
    const fetchJson = vi.fn();
    const full = { tracks: [track("a")], nextOffset: 1, hasMore: true, seen: null };
    const done = { tracks: [track("a")], nextOffset: 1, hasMore: false, seen: null };

    expect(await topUpTrackPage({}, full, { pageSize: 1, fetchJson })).toBe(full);
    expect(await topUpTrackPage({}, done, { pageSize: 10, fetchJson })).toBe(done);
    expect(fetchJson).not.toHaveBeenCalled();
  });
});

// A Dashboard with 50+ rows renders in about 3 s on its own; a loaded runner needs more room.
describe("Dashboard track list paging", { timeout: 20_000 }, () => {
  let server;

  beforeEach(() => {
    credentials.set({ url: "", username: "demo-user", password: "pw" });
    subsonicToken.set({ username: "demo-user", token: "test-subsonic-token" });
    viewMode.set("songs");
    deduplicateEnabled.set(false);
    favoriteGenres.set([]);
    memoriesOnHomeEnabled.set(false);
    // Not one of the offered sizes: a short top-up keeps the rendered list small and the tests fast.
    trackPageSize.set(60);
    resetFeedsCache();
    trackListCache.clear();
    server = heldFetch();
    globalThis.fetch = server.fetch;
    // The scroll sentinel never fires here: every request in these tests is the page's own.
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
  });

  afterEach(() => {
    trackPageSize.set(50);
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows the first 50 rows before the rest of a 60-row page is asked", async () => {
    render(Dashboard, { activeView: "genre:Hardcore" });

    await waitFor(() => expect(server.calls()).toHaveLength(1), SLOW);
    const first = query(server.calls()[0]);
    expect(first.get("count")).toBe("50");
    expect(first.get("offset")).toBe("0");

    server.answer("genre=Hardcore", tracks("h", 50), { moreResults: true, nextOffset: 50 });
    expect(await screen.findByText("Title h0", {}, SLOW)).toBeTruthy();
    expect(screen.queryByTestId("skeleton-rows")).toBeNull();

    // The rest of the page follows behind the rows on screen, from where the first answer stopped.
    await waitFor(() => expect(server.calls()).toHaveLength(2), SLOW);
    const rest = query(server.calls()[1]);
    expect(rest.get("offset")).toBe("50");
    expect(rest.get("count")).toBe("10");

    server.answer("genre=Hardcore", tracks("r", 10), { moreResults: true, nextOffset: 60 });
    expect(await screen.findByText("Title r9", {}, SLOW)).toBeTruthy();
    expect(screen.getByText("Title h0")).toBeTruthy();
  });

  it("folds versions together across the first page and its top-up", async () => {
    deduplicateEnabled.set(true);
    render(Dashboard, { activeView: "genre:Hardcore" });

    await waitFor(() => expect(server.calls()).toHaveLength(1), SLOW);
    const firstRows = tracks("h", 49).concat(track("orig", { workId: 7 }));
    server.answer("genre=Hardcore", firstRows, { moreResults: true, nextOffset: 50 });
    expect(await screen.findByText("Title orig", {}, SLOW)).toBeTruthy();

    await waitFor(() => expect(server.calls()).toHaveLength(2), SLOW);
    const restRows = [track("dupe", { workId: 7 }), ...tracks("r", 9)];
    server.answer("genre=Hardcore", restRows, { moreResults: false, nextOffset: 60 });

    expect(await screen.findByText("Title r8", {}, SLOW)).toBeTruthy();
    expect(screen.queryByText("Title dupe")).toBeNull();
    expect(screen.getAllByText("Title orig")).toHaveLength(1);
  });

  it("shows a revisited list whole from the cache, without asking again", async () => {
    const { rerender } = render(Dashboard, { activeView: "genre:Hardcore" });
    await waitFor(() => expect(server.calls()).toHaveLength(1), SLOW);
    server.answer("genre=Hardcore", tracks("h", 50), { moreResults: true, nextOffset: 50 });
    await waitFor(() => expect(server.calls()).toHaveLength(2), SLOW);
    server.answer("genre=Hardcore", tracks("r", 10), { moreResults: false, nextOffset: 60 });
    expect(await screen.findByText("Title r9", {}, SLOW)).toBeTruthy();

    await rerender({ activeView: "genre:Uptempo" });
    await rerender({ activeView: "genre:Hardcore" });

    // Both halves of the page are on screen in the first frame, and nothing was asked for them.
    expect(screen.getByText("Title h0")).toBeTruthy();
    expect(screen.getByText("Title r9")).toBeTruthy();
    expect(screen.queryByTestId("skeleton-rows")).toBeNull();
    expect(server.calls().filter((url) => url.includes("genre=Hardcore"))).toHaveLength(2);
  });

  it("aborts the request of a list the listener left for another list", async () => {
    const { rerender } = render(Dashboard, { activeView: "genre:Hardcore" });
    await waitFor(() => expect(server.pending).toHaveLength(1), SLOW);
    const hardcore = server.pending[0];

    await rerender({ activeView: "genre:Uptempo" });

    expect(hardcore.signal?.aborted).toBe(true);
    await waitFor(() =>
      expect(server.calls().some((url) => url.includes("genre=Uptempo"))).toBe(true),
    );
  });

  it("aborts the list request when the listener leaves the track lists altogether", async () => {
    const { rerender } = render(Dashboard, { activeView: "songs" });
    await waitFor(() => expect(server.pending).toHaveLength(1), SLOW);
    const songs = server.pending[0];

    await rerender({ activeView: "albums" });

    expect(songs.signal?.aborted).toBe(true);
  });

  it("aborts the top-up when the listener moves on before it is answered", async () => {
    const { rerender } = render(Dashboard, { activeView: "genre:Hardcore" });
    await waitFor(() => expect(server.calls()).toHaveLength(1), SLOW);
    server.answer("genre=Hardcore", tracks("h", 50), { moreResults: true, nextOffset: 50 });
    await waitFor(() => expect(server.pending).toHaveLength(1), SLOW);
    const topUp = server.pending[0];
    expect(query(topUp.url).get("offset")).toBe("50");

    await rerender({ activeView: "albums" });

    expect(topUp.signal?.aborted).toBe(true);
  });
});
